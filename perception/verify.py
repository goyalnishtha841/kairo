"""Temporal verification: a hand is accepted from its track over time, not from one frame.

The detector runs at a low threshold to find hard hands (see hands.make_landmarker), so single frames
flicker: a hand disappears for one frame and comes back, or a blip appears for one frame and is gone.
This pass works on hands.json, per hand id:

    1. tracklets      contiguous detections, split where the palm teleports (faster than a hand moves)
    2. linking        join two tracklets across a short gap when the motion is consistent: the next
                      tracklet starts where the previous one was heading (constant velocity) and the
                      palm has a similar size (same distance from the camera)
    3. verification   a linked track is accepted only with enough evidence: several detections, or one
                      very confident one. Short low-evidence tracks are rejected as false positives.
    4. bridging       gaps inside an accepted track are filled by interpolation, marked "bridged"

Usage:
    python perception/verify.py MTL-SGF00106-021   rewrite hands.json, keep the detector output in hands_raw.json
    python perception/verify.py --report           outputs/verification.json: flicker + human-label check
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"

ASPECT = 9 / 16           # y is normalised by height; distances are in frame widths
MAX_SPEED = 4.0           # frame widths/s: a palm moving faster than this between frames is a different object
MAX_GAP_S = 0.6           # longest dropout we bridge (bridges checked by eye: ~29/32 sit on a real hand)
LINK_TOL = 0.06           # frame widths: allowed miss of the constant-velocity prediction ...
LINK_TOL_PER_S = 0.5      # ... growing with the gap length
MIN_LINK_OBS = 2          # both sides of a bridge need this many detections (evidence for the motion)
SCALE_RATIO = 1.5         # palm size may change by at most this factor across a gap
MIN_OBS = 2               # detections a track needs to be accepted ...
SOLO_CONF = 0.7           # ... unless its best detection is at least this confident.
# Measured on human labels: rejecting longer or more confident short tracks removed real hands
# (brief appearances are usually real), so only one-frame, low-confidence blips are rejected.
BRIDGE_DECAY = 0.9        # score of a bridged frame = this x the weaker end


def _palm(lm):
    lm = np.asarray(lm)
    return lm[[0, 5, 9, 13, 17], :2].mean(0) * [1.0, ASPECT]


def _size(lm):
    lm = np.asarray(lm)
    return float(np.linalg.norm((lm[0, :2] - lm[9, :2]) * [1.0, ASPECT]))


def tracklets(seq, t):
    """seq: per frame the hand dict or None. Returns [[frame indices]] of contiguous, physically
    plausible detections."""
    out, cur = [], []
    for i, h in enumerate(seq):
        if h is None:
            if cur:
                out.append(cur)
            cur = []
            continue
        if cur:
            j = cur[-1]
            speed = np.linalg.norm(_palm(h["lm"]) - _palm(seq[j]["lm"])) / max(t[i] - t[j], 1e-6)
            if speed > MAX_SPEED:
                out.append(cur)
                cur = []
        cur.append(i)
    if cur:
        out.append(cur)
    return out


def _velocity(seq, t, idx):
    """Palm velocity at the end of a tracklet (frame widths/s), from up to its last 3 detections."""
    k = idx[-3:]
    if len(k) < 2:
        return np.zeros(2)
    return (_palm(seq[k[-1]]["lm"]) - _palm(seq[k[0]]["lm"])) / max(t[k[-1]] - t[k[0]], 1e-6)


def consistent(seq, t, a, b):
    """Can tracklet b continue tracklet a? (short gap, on the predicted path, similar palm size)"""
    if min(len(a), len(b)) < MIN_LINK_OBS:   # a one-frame piece has no velocity to check against
        return False
    i, j = a[-1], b[0]
    gap = t[j] - t[i]
    if gap > MAX_GAP_S + 1e-6:
        return False
    pred = _palm(seq[i]["lm"]) + _velocity(seq, t, a) * gap
    miss = float(np.linalg.norm(_palm(seq[j]["lm"]) - pred))
    if miss > LINK_TOL + LINK_TOL_PER_S * gap:
        return False
    r = _size(seq[j]["lm"]) / max(_size(seq[i]["lm"]), 1e-6)
    return 1 / SCALE_RATIO <= r <= SCALE_RATIO


def verify_hand(seq, t):
    """Returns (new_seq, stats) for one hand id."""
    parts = tracklets(seq, t)
    tracks = []
    for p in parts:
        if tracks and consistent(seq, t, tracks[-1][-1], p):
            tracks[-1].append(p)
        else:
            tracks.append([p])
    new = [None] * len(seq)
    stats = {"rejected": 0, "bridged": 0, "tracks": 0, "linked_gaps": 0}
    seen = [i for i, h in enumerate(seq) if h is not None]
    for tr in tracks:
        idx = [i for p in tr for i in p]
        best = max(seq[i]["score"] for i in idx)
        # isolated: no other detection of this hand within MAX_GAP_S
        near = [k for k in seen if k not in idx and min(abs(t[k] - t[idx[0]]), abs(t[k] - t[idx[-1]])) <= MAX_GAP_S]
        if len(idx) < MIN_OBS and best < SOLO_CONF and not near:
            stats["rejected"] += len(idx)
            continue
        stats["tracks"] += 1
        for i in idx:
            new[i] = dict(seq[i])
        for a, b in zip(tr, tr[1:]):
            i, j = a[-1], b[0]
            stats["linked_gaps"] += 1
            la, lb = np.asarray(seq[i]["lm"]), np.asarray(seq[j]["lm"])
            ra, rb = np.asarray(seq[i]["lm_raw"]), np.asarray(seq[j]["lm_raw"])
            for k in range(i + 1, j):
                w = (t[k] - t[i]) / (t[j] - t[i])
                new[k] = {"score": round(BRIDGE_DECAY * min(seq[i]["score"], seq[j]["score"]), 3),
                          "lm": np.round((1 - w) * la + w * lb, 4).tolist(),
                          "lm_raw": np.round((1 - w) * ra + w * rb, 4).tolist(),
                          "bridged": True}
                stats["bridged"] += 1
    return new, stats


def verify_frames(frames):
    """Temporal verification of every hand id in a hands.json frame list. Returns (frames, stats)."""
    t = np.array([f["t"] for f in frames])
    out = [dict(f, hands=[]) for f in frames]
    total = {"detections_in": sum(len(f["hands"]) for f in frames)}
    for hid in ("L", "R"):
        seq = [next((h for h in f["hands"] if h["id"] == hid), None) for f in frames]
        new, st = verify_hand(seq, t)
        for k, v in st.items():
            total[k] = total.get(k, 0) + v
        for i, h in enumerate(new):
            if h is not None:
                out[i]["hands"].append({"id": hid, **{k: v for k, v in h.items() if k != "id"}})
    total["detections_out"] = sum(len(f["hands"]) for f in out)
    total["flicker_before"] = flicker(frames)
    total["flicker_after"] = flicker(out)
    return out, total


def flicker(frames):
    """Presence on/off switches per minute, per hand id (lower = steadier)."""
    if len(frames) < 2:
        return 0.0
    sw = 0
    for hid in ("L", "R"):
        pres = [any(h["id"] == hid for h in f["hands"]) for f in frames]
        sw += sum(a != b for a, b in zip(pres, pres[1:]))
    mins = max((frames[-1]["t"] - frames[0]["t"]) / 60, 1e-6)
    return round(sw / mins, 1)


def raw_frames(clip_id):
    """The detector's unverified frames for a clip (hands_raw.json once verified, else hands.json)."""
    d = OUT / clip_id
    p = d / "hands_raw.json" if (d / "hands_raw.json").exists() else d / "hands.json"
    return json.loads(p.read_text())["frames"]


def apply(clip_id, fresh=False):
    """Verify hands.json in place and record stats. Idempotent: always starts from hands_raw.json;
    pass fresh=True right after the tracker rewrote hands.json, so the new tracks become the raw copy."""
    d = OUT / clip_id
    raw_p, p = d / "hands_raw.json", d / "hands.json"
    if fresh or not raw_p.exists():
        raw_p.write_text(p.read_text())
    data = json.loads(raw_p.read_text())
    data["frames"], stats = verify_frames(data["frames"])
    data["verification"] = stats
    p.write_text(json.dumps(data))
    m = d / "metrics.json"
    if m.exists():
        metrics = json.loads(m.read_text())
        metrics["verification"] = stats
        n = max(len(data["frames"]), 1)
        metrics["detection_rate_any_hand_verified"] = round(sum(bool(f["hands"]) for f in data["frames"]) / n, 4)
        m.write_text(json.dumps(metrics, indent=2))
    return stats


# ---------------------------------------------------------------- measured against human labels
EVAL = ROOT / "eval"


def label_check(set_prefix=""):
    """Raw vs verified detections on the human-labelled frames of eval/accuracy.py.

    Labels are per-frame counts (visible wearer hands, correct skeletons), so for a changed frame:
      * a rejected detection counts as a lost true hand unless the frame had a known false one;
      * a bridged detection counts as found only if a labelled hand was missed there. Whether the
        bridged skeleton sits on that hand was checked by eye (~29 of 32 did), so recall is reported
        as a range: all bridges right / all bridges wrong.
    """
    items = {it["id"]: it for it in json.loads((EVAL / f"{set_prefix}sample.json").read_text())}
    labels = {int(k): v for k, v in json.loads((EVAL / f"{set_prefix}labels.json").read_text()).items()
              if v.get("correct") is not None}
    cache = {}
    det0 = det1 = gt = c0 = c_lo = c_hi = pres0 = pres1 = added = removed = 0
    for i, lab in labels.items():
        it = items[i]
        c = it["clip_id"]
        if c not in cache:
            fr = raw_frames(c)
            cache[c] = {f["frame"]: (f, v) for f, v in zip(fr, verify_frames(fr)[0])}
        raw, ver = cache[c][it["frame"]]
        ids0, ids1 = {h["id"] for h in raw["hands"]}, {h["id"] for h in ver["hands"]}
        add, rem = len(ids1 - ids0), len(ids0 - ids1)
        known_false = len(ids0) - lab["correct"]
        lost = max(0, rem - known_false)
        det0 += len(ids0)
        det1 += len(ids1)
        gt += lab["gt"]
        c0 += lab["correct"]
        c_lo += lab["correct"] - lost
        c_hi += lab["correct"] - lost + min(add, max(0, lab["gt"] - lab["correct"]))
        pres0 += (len(ids0) > 0) == (lab["gt"] > 0)
        pres1 += (len(ids1) > 0) == (lab["gt"] > 0)
        added += add
        removed += rem
    n = max(len(labels), 1)
    r = lambda x: round(x, 3)
    return {"frames": len(labels), "bridged_detections": added, "rejected_detections": removed,
            "before": {"precision": r(c0 / det0) if det0 else None, "recall": r(c0 / gt) if gt else None,
                       "frame_presence": r(pres0 / n)},
            "after": {"precision": r(c_hi / det1) if det1 else None, "recall": r(c_hi / gt) if gt else None,
                      "recall_if_bridges_wrong": r(c_lo / gt) if gt else None, "frame_presence": r(pres1 / n)}}


def report(clips=None):
    """Flicker and verification counts over every processed clip, plus the label checks."""
    clips = clips or sorted(q.parent.name for q in OUT.glob("*/hands.json") if not q.parent.name.startswith("zz-"))
    per, tot = [], {}
    for c in clips:
        _, st = verify_frames(raw_frames(c))
        per.append({"clip_id": c, **st})
        for k in ("detections_in", "detections_out", "bridged", "rejected", "linked_gaps"):
            tot[k] = tot.get(k, 0) + st[k]
    n = max(len(per), 1)
    tot["flicker_before"] = round(sum(x["flicker_before"] for x in per) / n, 1)
    tot["flicker_after"] = round(sum(x["flicker_after"] for x in per) / n, 1)
    tot["flicker_reduction_pct"] = round(100 * (1 - tot["flicker_after"] / tot["flicker_before"]))         if tot["flicker_before"] else None
    out = {"clips": per, "total": tot,
           "params": {"max_gap_s": MAX_GAP_S, "min_obs": MIN_OBS, "solo_conf": SOLO_CONF, "max_speed": MAX_SPEED},
           "rejection_check": "Only isolated blips are rejected (no other detection of that hand within the gap). "
                              "Under a broader version of the rule, 16 random rejections were checked by eye: ~13 were not "
                              "the wearer's hand (chairs, wood, a box, coworkers' hands)."}
    for name, pre in (("tune", ""), ("heldout", "heldout_")):
        if (EVAL / f"{pre}labels.json").exists():
            out[name] = label_check(pre)
    return out


if __name__ == "__main__":
    if sys.argv[1:] == ["--report"]:
        res = report()
        (OUT / "verification.json").write_text(json.dumps(res, indent=1))
        print(json.dumps({k: v for k, v in res.items() if k != "clips"}, indent=1))
    else:
        for c in sys.argv[1:]:
            print(c, apply(c))
