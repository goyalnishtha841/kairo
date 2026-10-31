"""Collaboration Intelligence: high-precision collaboration EVENTS (never conversation content).

Pipeline per 0.5 s window, from perception/social.py + the timeline:
  1 present  another person in view (the wearer's own body excluded)
  2 near     that person is close (large box or large face)
  3 facing   their face is turned toward the wearer
  4 speech   voice activity clearly above this clip's background (adaptive, so machine noise does not count)
  5 paused   the wearer's work pauses (hands out of view or still)
  6 context  work resumes afterwards (checked per event)

Precision first: signals are smoothed in time, an event needs hysteresis (start high, stay above a lower
bar), a minimum duration, and a mandatory agreement of several signals. Confidence >= 0.90 ->
"collaboration", 0.60-0.90 -> "possible_collaboration", below -> dropped. A false event is worse than a
missed one.

Usage: python events/collaboration.py MTL-SGF00106-021      (adds events to its timeline.json)
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

WIN = 0.5
WEIGHTS = {"present": 0.10, "near": 0.20, "facing": 0.30, "speech": 0.20, "paused": 0.20}
ENTER, STAY = 0.65, 0.45        # hysteresis on the smoothed window score
MIN_DURATION_S = 3.0
MERGE_GAP_S = 2.0
NEAR_AREA, NEAR_FACE = 0.08, 0.04
TYPES = ("collaboration", "possible_collaboration")


def _smooth(x, k=3, how="max"):
    pad = k // 2
    xp = np.pad(np.asarray(x, float), pad, mode="edge")
    f = np.max if how == "max" else np.mean
    return np.array([f(xp[i:i + k]) for i in range(len(x))])


def signals(social, timeline):
    """Per-window boolean/float signals aligned on 0.5 s windows."""
    n = int(np.ceil(timeline["duration_s"] / WIN))
    present, near, facing = np.zeros(n), np.zeros(n), np.zeros(n)
    for s in social["samples"]:
        k = min(n - 1, int(s["t"] / WIN))
        if s["persons"] or s["faces"]:
            present[k] = 1
        if any(p["area"] >= NEAR_AREA for p in s["persons"]) or any(f["width"] >= NEAR_FACE for f in s["faces"]):
            near[k] = 1
        if any(f["frontal"] and f["width"] >= 0.03 for f in s["faces"]):
            facing[k] = 1
    sp = np.zeros(n)
    if social.get("speech"):
        raw = np.array((social["speech"] + [0] * n)[:n], float)
        # adaptive: speech must stand clearly above this clip's typical level (noisy clips -> ~never)
        thr = max(0.6, float(np.percentile(raw, 60)) + 0.3)
        sp = (raw >= thr).astype(float)
    paused = np.ones(n)
    for st in timeline["states"]:
        if st["state"] == "work":
            a, b = int(st["t_start"] / WIN), int(np.ceil(st["t_end"] / WIN))
            paused[a:b] = 0
    # flicker-tolerant: faces/persons drop out for a frame at 2 fps; speech has pauses between words
    return {"present": _smooth(present, 3, "max"), "near": _smooth(near, 3, "max"),
            "facing": _smooth(facing, 3, "max"), "speech": _smooth(sp, 5, "max"), "paused": paused}


def detect(social, timeline):
    sig = signals(social, timeline)
    n = len(sig["paused"])
    score = sum(WEIGHTS[k] * sig[k] for k in WEIGHTS)
    score = _smooth(score, 3, "mean")

    # hysteresis: start after 2 windows >= ENTER, continue while >= STAY
    spans, start, below = [], None, 0
    for i in range(n):
        if start is None:
            if i > 0 and score[i] >= ENTER and score[i - 1] >= ENTER:
                start, below = i - 1, 0
        else:
            below = below + 1 if score[i] < STAY else 0
            if below >= 2:
                spans.append([start, i - 2])
                start = None
    if start is not None:
        spans.append([start, n - 1])

    merged = []
    for a, b in spans:
        if merged and (a - merged[-1][1]) * WIN <= MERGE_GAP_S:
            merged[-1][1] = b
        else:
            merged.append([a, b])

    work = np.array([1 - p for p in sig["paused"]])
    events = []
    for a, b in merged:
        dur = (b - a + 1) * WIN
        if dur < MIN_DURATION_S:
            continue
        frac = {k: round(float(sig[k][a:b + 1].mean()), 2) for k in WEIGHTS}
        # mandatory multi-signal agreement: someone facing the wearer, work paused, and speech or proximity
        if not (frac["facing"] >= 0.4 and frac["paused"] >= 0.5 and (frac["speech"] >= 0.4 or frac["near"] >= 0.5)):
            continue
        resumes = bool(work[b + 1:b + 1 + int(10 / WIN)].any())
        conf = float(score[a:b + 1].mean()) + (0.05 if resumes else -0.1) + (0.05 if dur >= 6 else 0)
        conf = round(min(0.99, max(0.0, conf)), 2)
        if conf < C.COLLAB_POSSIBLE:
            continue
        typ = "collaboration" if conf >= C.COLLAB_CONFIRMED else "possible_collaboration"
        agree = [k for k in ("near", "facing", "speech", "paused") if frac[k] >= 0.5]
        events.append({"type": typ, "t_start": round(a * WIN, 2), "t_end": round((b + 1) * WIN, 2),
                       "confidence": conf, "evidence": {"signal_share": frac, "work_resumes": resumes},
                       "note": f"{'A collaboration event' if typ == 'collaboration' else 'A possible collaboration event'}"
                               f" ({dur:.0f}s): signals agree on {', '.join(agree)}"
                               + ("; work resumes afterwards" if resumes else "")})
    return events


def apply(clip_id):
    """Add collaboration events to a clip's timeline (idempotent)."""
    tl_path, so_path = OUT / clip_id / "timeline.json", OUT / clip_id / "social.json"
    if not so_path.exists():
        return []
    tl = json.loads(tl_path.read_text())
    social = json.loads(so_path.read_text())
    found = detect(social, tl)
    tl["events"] = [e for e in tl["events"] if e["type"] not in TYPES]
    n0 = len(tl["events"])
    for i, e in enumerate(found):
        tl["events"].append({"id": f"c{i + 1:03d}", "t_start": e["t_start"], "t_end": e["t_end"], "type": e["type"],
                             "hand": None, "tool": None, "zone": None, "step_id": None, "cycle_id": None,
                             "confidence": e["confidence"], "note": e["note"], "severity": "blue",
                             "evidence": e["evidence"]})
    tl["events"].sort(key=lambda e: e["t_start"])
    tl_path.write_text(json.dumps(tl, indent=1))
    return found


if __name__ == "__main__":
    for c in sys.argv[1:]:
        ev = apply(c)
        print(c, len(ev), "events", [(e["type"], e["t_start"], e["t_end"], e["confidence"]) for e in ev])
