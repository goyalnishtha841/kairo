"""Merge perception/tools.py's open-vocabulary detections onto timeline.json: for each SOP step,
find the tool label most often detected near the working hand during that step.

Writes `tool_detected` (never overwrites the existing VLM-captioned `tool` field, which is a
different, separately-unvalidated guess -- the two are kept distinguishable rather than silently
replacing one unverified source with another) plus `tool_detected_confidence` and a fixed honesty
note on every step. Idempotent, same pattern as events/collaboration.py's apply().

Usage: python events/apply_tools.py <clip_id>
"""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402

NOTE = "Open-vocabulary detection (YOLO-World), unvalidated: no labelled footage exists to measure precision/recall against."


def _hand_positions(hands_data):
    """[(t, {"L": (x,y) or None, "R": (x,y) or None}), ...] per frame."""
    out = []
    for f in hands_data["frames"]:
        pos = {}
        for hd in f["hands"]:
            if hd.get("bridged"):
                continue
            lm = np.array(hd["lm"])
            pos[hd["id"]] = lm[[0, 5, 9, 13, 17], :2].mean(0)
        out.append((f["t"], pos))
    return out


def _nearest_hand_dist(cx, cy, hand_pos):
    best = None
    for p in hand_pos.values():
        d = float(np.hypot(p[0] - cx, p[1] - cy))
        if best is None or d < best:
            best = d
    return best


def tool_for_step(step, tool_samples, hand_frames):
    a, b = step["t_start"], step["t_end"]
    window_hands = [(t, hp) for t, hp in hand_frames if a <= t <= b and hp]
    if not window_hands:
        return None, 0.0
    labels = Counter()
    confs = {}
    for s in tool_samples:
        if not (a <= s["t"] <= b) or not s["detections"]:
            continue
        # nearest-time hand frame (hand_frames is sampled at ~15fps, tool samples at ~2fps)
        _, hp = min(window_hands, key=lambda th: abs(th[0] - s["t"]))
        for d in s["detections"]:
            dist = _nearest_hand_dist(d["cx"], d["cy"], hp)
            if dist is not None and dist <= C.TOOL_HAND_MAX_DIST:
                labels[d["label"]] += 1
                confs.setdefault(d["label"], []).append(d["score"])
    if not labels:
        return None, 0.0
    top, _ = labels.most_common(1)[0]
    return top, round(float(np.mean(confs[top])), 2)


def apply(clip_id):
    tl_path, tools_path, hands_path = (OUT / clip_id / f for f in ("timeline.json", "tools.json", "hands.json"))
    if not tools_path.exists() or not hands_path.exists():
        return 0
    tl = json.loads(tl_path.read_text())
    tools = json.loads(tools_path.read_text())
    hands_data = json.loads(hands_path.read_text())
    hand_frames = _hand_positions(hands_data)

    n = 0
    for step in tl["steps"]:
        label, conf = tool_for_step(step, tools["samples"], hand_frames)
        step["tool_detected"] = label
        step["tool_detected_confidence"] = conf
        step["tool_detection_note"] = NOTE if label else None
        if label:
            n += 1
    tl_path.write_text(json.dumps(tl, indent=1))
    return n


if __name__ == "__main__":
    n = apply(sys.argv[1])
    print(f"{sys.argv[1]}: tool detected in {n} step(s)")
