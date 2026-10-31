"""Worker Attention Analysis (USP 8): where the head-mounted camera was pointed, as a time-in-zone
heatmap. Built only from signals Kairo already measures:

  machine        hands in view, working (the camera typically looks at the workpiece while hands work)
  tool_search_*  head scanning while hands are out of view and searching, by zone (left/center/right)
  colleague      head toward another person, from a collaboration event (perception/social.py)
  floor_or_away  hands out of view, head still, no one present (idle with no collaboration signal)

We do not report a "phone" zone: there is no object detector for a phone in this stack, and inventing
one would be exactly the kind of unverifiable claim docs/STRATEGY.md says to cut. If that detector
ships, add it here instead of guessing.

Usage: python events/attention.py <clip_id>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"

NOT_DETECTED = ["phone"]


def load(clip_id):
    return json.loads((OUT / clip_id / "timeline.json").read_text())


def heatmap(clip_id):
    tl = load(clip_id)
    collab_spans = [(e["t_start"], e["t_end"]) for e in tl["events"]
                     if e["type"] in ("collaboration", "possible_collaboration")]

    def overlaps_collab(a, b):
        return any(a < ce and b > cs for cs, ce in collab_spans)

    def search_zone(a):
        for e in tl["events"]:
            if e["type"] == "search" and e["t_start"] <= a < e["t_end"] and e.get("zone"):
                return e["zone"]
        return None

    zones = {"machine": 0.0, "tool_search_left": 0.0, "tool_search_center": 0.0, "tool_search_right": 0.0,
              "colleague": 0.0, "floor_or_away": 0.0}
    for s in tl["states"]:
        a, b = s["t_start"], s["t_end"]
        dur = b - a
        if s["state"] == "work":
            zones["machine"] += dur
        elif overlaps_collab(a, b):
            zones["colleague"] += dur
        elif s["state"] in ("search", "transit"):
            z = search_zone(a)
            zones[f"tool_search_{z}" if z in ("left", "right") else "tool_search_center"] += dur
        else:  # idle, no collaboration signal
            zones["floor_or_away"] += dur

    total = tl["duration_s"] or 1.0
    return {"clip_id": clip_id, "duration_s": tl["duration_s"],
            "seconds": {k: round(v, 1) for k, v in zones.items()},
            "pct": {k: round(100 * v / total, 1) for k, v in zones.items()},
            "not_detected": NOT_DETECTED,
            "note": "Zones come from hand visibility, head scanning and collaboration signals, not gaze "
                    "tracking or a phone/object detector."}


if __name__ == "__main__":
    print(json.dumps(heatmap(sys.argv[1]), indent=1))
