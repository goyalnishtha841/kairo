"""Event timeline engine: hands.json (+ head motion) -> timeline.json (see schema/timeline.md).

Activity states per sample:
    work     hands in view (manipulating / holding)
    search   hands out of view + head scanning, short   -> friction (red)
    transit  hands out of view + moving, long (walking) -> friction (red)
    idle     hands out of view, head still               -> friction (yellow)
Friction inside work:
    hesitation   hand stalls between two movements
    extra_reach  hand path much longer than the straight line

Usage:
    python events/timeline.py MTL-SGF00106-021 [--keyframes]
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
RAW = ROOT / "data" / "raw"

FOV_DEG = 150.0          # approx horizontal FOV of the fisheye head cam
HEAD_SCAN = 0.35         # frame-widths/s of pan+tilt that counts as scanning
SEARCH_MAX_S = 8.0       # out-of-view motion longer than this is transit, not search
MIN_SEG_S = 0.8          # shorter state blips are absorbed by neighbours
STEP_GAP_S = 1.5         # non-work gap that splits two SOP steps
MIN_STEP_S = 2.0
# hand speed in frame-widths/s; calibrated on SGF00106 (median 0.08, p75 0.15 while hands visible)
V_MOVE = 0.10            # counts as moving
V_STALL = 0.03           # below this the hand is stalled
MIN_STALL_SEEN = 0.7     # share of a stall the hand must be measured in (else it is a dropout)
# reattempt: the hand keeps returning to about the same spot (pick / put back / pick again), a
# hidden correction cycle the worker rarely notices themself
REATTEMPT_TOUCH_S = 0.25     # minimum time still-in-place to count as one "touch" of the part
REATTEMPT_GAP_S = 2.5        # max time between touches to call them the same cluster
REATTEMPT_DIST = 0.05        # frame-widths: touches this close together count as "the same spot"
REATTEMPT_MIN_TOUCHES = 3    # >=3 touches = at least 2 unnecessary re-grasps
FRICTION = {"search", "transit", "idle", "hesitation", "extra_reach", "reattempt"}
SEVERITY = {"search": "red", "transit": "red", "idle": "yellow", "hesitation": "yellow",
            "extra_reach": "yellow", "reattempt": "yellow"}


def rolling_median(x, k):
    if k <= 1:
        return x
    pad = k // 2
    xp = np.pad(x, pad, mode="edge")
    return np.array([np.median(xp[i:i + k]) for i in range(len(x))])


def load_signals(hands):
    fr = hands["frames"]
    t = np.array([f["t"] for f in fr])
    n_hands = np.array([len(f["hands"]) for f in fr])
    head = np.array([abs(f["cam"]["pan"]) + abs(f["cam"]["tilt"]) if f.get("cam") else 0.0 for f in fr])
    pan = np.array([f["cam"]["pan"] if f.get("cam") else 0.0 for f in fr])
    # per-hand palm centre (mean of wrist + MCPs) to get speed and position
    pos = {h: np.full((len(fr), 2), np.nan) for h in ("L", "R")}
    for i, f in enumerate(fr):
        for hd in f["hands"]:
            if hd.get("bridged"):  # verified presence, but interpolated: never motion evidence
                continue
            lm = np.array(hd["lm"])
            pos[hd["id"]][i] = lm[[0, 5, 9, 13, 17], :2].mean(0)
    dt = np.gradient(t) if len(t) > 1 else np.ones_like(t)
    speed = np.zeros(len(fr))
    for h in pos:
        v = np.linalg.norm(np.gradient(pos[h], axis=0), axis=1) / dt
        speed = np.fmax(speed, np.nan_to_num(v, nan=0.0))
    return t, n_hands, head, pan, pos, speed


def segments(labels, t):
    segs, start = [], 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            segs.append([labels[start], start, i - 1])
            start = i
    return segs


def absorb_short(segs, t, min_s):
    changed = True
    while changed and len(segs) > 1:
        changed = False
        for k, (lab, a, b) in enumerate(segs):
            if t[b] - t[a] < min_s:
                nb = segs[k - 1] if k > 0 else segs[k + 1]
                if k > 0 and (k + 1 == len(segs) or t[segs[k - 1][2]] - t[segs[k - 1][1]] >=
                              t[segs[k + 1][2]] - t[segs[k + 1][1]]):
                    segs[k - 1][2] = b
                else:
                    segs[k + 1][1] = a
                segs.pop(k)
                changed = True
                break
    # merge equal neighbours
    out = [segs[0]]
    for s in segs[1:]:
        if s[0] == out[-1][0]:
            out[-1][2] = s[2]
        else:
            out.append(s)
    return out


def motion_label(hand, active):
    """Fallback step name from hand usage; replaced by VLM captions (ai/sop_labels.py) when available."""
    side = {"L": "Left-hand", "R": "Right-hand"}.get(hand)
    if hand == "both":
        return "Two-handed manipulation" if active >= 0.35 else "Hold & align (two hands)"
    return f"{side} tool work" if active >= 0.35 else f"{side} positioning"


def zone_of(x):
    if x is None or np.isnan(x):
        return None
    return "left" if x < 0.36 else "right" if x > 0.64 else "center"


def build(clip_id, keyframes=False):
    hands = json.loads((OUT / clip_id / "hands.json").read_text())
    fps = hands["fps"]
    t, n_hands, head, pan, pos, speed = load_signals(hands)
    bridged_only = np.array([bool(f["hands"]) and all(h.get("bridged") for h in f["hands"])
                             for f in hands["frames"]])
    hz = 1.0 / max(np.median(np.diff(t)), 1e-3)
    k = max(1, int(round(0.5 * hz)) | 1)
    vis = rolling_median(n_hands.astype(float), k) >= 0.5
    head_s = rolling_median(head, k)
    speed_s = rolling_median(speed, k)

    raw = np.where(vis, "work", np.where(head_s > HEAD_SCAN, "search", "idle"))
    segs = absorb_short(segments([str(x) for x in raw], t), t, MIN_SEG_S)

    events, steps = [], []
    eid = 0

    def add(typ, a, b, **kw):
        nonlocal eid
        eid += 1
        ev = {"id": f"e{eid:04d}", "t_start": round(float(t[a]), 2), "t_end": round(float(t[b]), 2),
              "type": typ, "hand": kw.get("hand"), "tool": None, "zone": kw.get("zone"),
              "step_id": kw.get("step_id"), "cycle_id": None,
              "confidence": round(float(kw.get("conf", 0.6)), 2), "note": kw.get("note"),
              "severity": SEVERITY.get(typ, "green")}
        events.append(ev)
        return ev

    # --- out-of-view states -------------------------------------------------
    state_segs = []
    for lab, a, b in segs:
        dur = t[b] - t[a]
        if lab == "search" and dur > SEARCH_MAX_S:
            lab = "transit"
        state_segs.append((lab, a, b))
        if lab == "work":
            continue
        turn = float(np.sum(pan[a:b + 1]) * np.median(np.diff(t))) * FOV_DEG
        direction = "left" if turn < -15 else "right" if turn > 15 else None
        if lab == "search":
            # angle is a rough estimate (fisheye + moving people inflate it), so cap the wording
            amount = "looking all around" if abs(turn) > 180 else f"~{abs(turn):.0f}° {direction}"
            note = f"hands out of view, head scanning{(' ' + amount) if direction else ''}"
            conf = min(0.95, 0.5 + float(np.mean(head_s[a:b + 1])))
        elif lab == "transit":
            note = f"away from work for {dur:.1f}s (walking / fetching)"
            conf = 0.7
        else:
            note = f"hands out of view, head still for {dur:.1f}s (waiting / talking)"
            conf = 0.65
        add(lab, a, b, zone=direction, conf=conf, note=note)

    # --- SOP steps = work blocks split by gaps >= STEP_GAP_S ------------------
    blocks = []
    for lab, a, b in state_segs:
        if lab != "work":
            continue
        if blocks and t[a] - t[blocks[-1][1]] < STEP_GAP_S:
            blocks[-1][1] = b
        else:
            blocks.append([a, b])
    blocks = [bl for bl in blocks if t[bl[1]] - t[bl[0]] >= MIN_STEP_S]

    for sid, (a, b) in enumerate(blocks, 1):
        xs = np.concatenate([pos[h][a:b + 1, 0] for h in pos])
        lr = {h: int(np.sum(~np.isnan(pos[h][a:b + 1, 0]))) for h in pos}
        dom = "both" if min(lr.values()) > 0.4 * max(lr.values()) else max(lr, key=lr.get)
        active = float(np.mean(speed_s[a:b + 1] > V_MOVE))
        # keyframe: the frame in the block with the most hands, nearest the middle
        mid = (a + b) // 2
        cand = [i for i in range(a, b + 1) if n_hands[i] == n_hands[a:b + 1].max()]
        kf = min(cand, key=lambda i: abs(i - mid))
        steps.append({"step_id": sid, "label": motion_label(dom, active),
                      "t_start": round(float(t[a]), 2), "t_end": round(float(t[b]), 2),
                      "duration_s": round(float(t[b] - t[a]), 2),
                      "hand": dom, "zone": zone_of(np.nanmedian(xs)) if np.any(~np.isnan(xs)) else None,
                      "active_ratio": round(active, 2),
                      "keyframe_t": round(float(t[kf]), 2), "keyframe": None})

        # hesitation: stall of 1-3 s between two movements, hands in view
        moving = speed_s[a:b + 1] > V_MOVE
        # bridged (interpolated) frames carry no speed evidence, so they never count as stalled
        stalled = (speed_s[a:b + 1] < V_STALL) & ~bridged_only[a:b + 1]
        measured = np.zeros(b - a + 1, bool)
        for h in pos:
            measured |= ~np.isnan(pos[h][a:b + 1, 0])
        i = 0
        while i < len(stalled):
            if stalled[i]:
                j = i
                while j + 1 < len(stalled) and stalled[j + 1]:
                    j += 1
                d = t[a + j] - t[a + i]
                before = moving[max(0, i - int(hz)):i].any()
                after = moving[j + 1:j + 1 + int(hz)].any()
                # a stall is only a hesitation if the hand was actually measured through it;
                # otherwise it is a tracking dropout (speed reads 0 where the hand is not detected)
                seen = float(np.mean(measured[i:j + 1]))
                if 1.0 <= d <= 3.0 and before and after and seen >= MIN_STALL_SEEN:
                    add("hesitation", a + i, a + j, step_id=sid, hand=dom,
                        conf=0.55, note=f"hand stalled {d:.1f}s between movements")
                i = j + 1
            else:
                i += 1

        # extra reach: one continuous movement whose path >> straight line
        for h in pos:
            p = pos[h][a:b + 1]
            mv = (speed_s[a:b + 1] > V_MOVE) & ~np.isnan(p[:, 0])
            i = 0
            while i < len(mv):
                if mv[i]:
                    j = i
                    while j + 1 < len(mv) and mv[j + 1]:
                        j += 1
                    seg = p[i:j + 1]
                    if len(seg) >= 4 and 0.4 <= t[a + j] - t[a + i] <= 4.0:
                        path = float(np.sum(np.linalg.norm(np.diff(seg, axis=0), axis=1)))
                        disp = float(np.linalg.norm(seg[-1] - seg[0]))
                        if path > 0.6 and disp > 0.05 and path / disp > 3.0:
                            add("extra_reach", a + i, a + j, step_id=sid, hand=h, conf=0.5,
                                zone=zone_of(seg[:, 0].mean()),
                                note=f"hand path {path / disp:.1f}x the straight line")
                    i = j + 1
                else:
                    i += 1

        # reattempt: the hand keeps settling back on about the same spot (pick / put back /
        # pick again / adjust / pick again) without the step ever finishing between touches
        for h in pos:
            p = pos[h][a:b + 1]
            measured = ~np.isnan(p[:, 0])
            stalled = (speed_s[a:b + 1] < V_STALL) & measured & ~bridged_only[a:b + 1]
            touches = []
            i = 0
            while i < len(stalled):
                if stalled[i]:
                    j = i
                    while j + 1 < len(stalled) and stalled[j + 1]:
                        j += 1
                    if t[a + j] - t[a + i] >= REATTEMPT_TOUCH_S:
                        touches.append((i, j, np.nanmean(p[i:j + 1], axis=0)))
                    i = j + 1
                else:
                    i += 1
            k = 0
            while k < len(touches):
                cluster = [touches[k]]
                m = k + 1
                while m < len(touches):
                    gap = t[a + touches[m][0]] - t[a + cluster[-1][1]]
                    dist = float(np.linalg.norm(touches[m][2] - cluster[-1][2]))
                    if gap <= REATTEMPT_GAP_S and dist <= REATTEMPT_DIST:
                        cluster.append(touches[m])
                        m += 1
                    else:
                        break
                if len(cluster) >= REATTEMPT_MIN_TOUCHES:
                    i0, j0 = cluster[0][0], cluster[-1][1]
                    conf = min(0.85, 0.35 + 0.1 * len(cluster))
                    add("reattempt", a + i0, a + j0, step_id=sid, hand=h, conf=conf,
                        zone=zone_of(float(np.mean([c[2][0] for c in cluster]))),
                        note=f"{len(cluster)} grasp/release-like cycles in place "
                             f"({len(cluster) - 1} unnecessary correction{'s' if len(cluster) > 2 else ''})")
                k = m if m > k else k + 1

    # tag events with the step they fall in
    for ev in events:
        if ev["step_id"] is None:
            for s in steps:
                if s["t_start"] <= ev["t_start"] <= s["t_end"]:
                    ev["step_id"] = s["step_id"]
    events.sort(key=lambda e: e["t_start"])

    if keyframes:
        save_keyframes(clip_id, steps, fps)

    states = [{"state": lab, "t_start": round(float(t[a]), 2), "t_end": round(float(t[b]), 2)}
              for lab, a, b in state_segs]
    tl = {"clip_id": clip_id, "fps": fps, "duration_s": hands.get("duration_s", round(float(t[-1]), 2)),
          "states": states, "steps": steps, "events": events,
          "signals": downsample_signals(t, vis, speed_s, head_s)}
    (OUT / clip_id / "timeline.json").write_text(json.dumps(tl, indent=1))
    return tl


def downsample_signals(t, vis, speed, head, hz=2.0):
    """Light per-0.5s signal for the UI sparkline."""
    out, step = [], 1.0 / hz
    edges = np.arange(0, t[-1] + step, step)
    for a, b in zip(edges[:-1], edges[1:]):
        m = (t >= a) & (t < b)
        if m.any():
            out.append([round(float(a), 1), round(float(vis[m].mean()), 2),
                        round(float(speed[m].mean()), 3), round(float(head[m].mean()), 3)])
    return out


def save_keyframes(clip_id, steps, fps):
    video = RAW / f"{clip_id}.mp4"
    if not video.exists():
        return
    d = OUT / clip_id / "frames"
    d.mkdir(exist_ok=True)
    cap = cv2.VideoCapture(str(video))
    for s in steps:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(s["keyframe_t"] * fps))
        ok, im = cap.read()
        if ok:
            im = cv2.resize(im, (640, 360))
            name = f"step{s['step_id']}.jpg"
            cv2.imwrite(str(d / name), im, [cv2.IMWRITE_JPEG_QUALITY, 85])
            s["keyframe"] = f"frames/{name}"
    cap.release()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("clip_id")
    ap.add_argument("--keyframes", action="store_true")
    a = ap.parse_args()
    tl = build(a.clip_id, a.keyframes)
    from collections import Counter
    print(f"{a.clip_id}: {len(tl['steps'])} steps, events {dict(Counter(e['type'] for e in tl['events']))}")
    tot = Counter()
    for s in tl["states"]:
        tot[s["state"]] += s["t_end"] - s["t_start"]
    print({k: f"{v:.0f}s" for k, v in tot.items()})
