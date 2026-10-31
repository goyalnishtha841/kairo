"""Human-like Memory (USP 20): remembers which SOP steps were already completed earlier in the shift,
across clips, so Kairo can say "already completed" instead of re-reporting the same bolt.

Chronological order comes from the caller's own `clip_ids` list (this module keeps no wall-clock
calendar of its own). Step matching reuses the same token-overlap similarity as events/compare.py and
events/sop.py, so caption wording differences don't cause a false "not done yet" -- but the match bar
is tighter here (MATCH_MIN), because a false "already completed" is worse than a false "not yet".

Usage: python events/memory.py "tighten bolt 4" <clip_id> [<clip_id> ...]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from insights import fmt_t  # noqa: E402

STOP = {"a", "an", "the", "with", "of", "to", "into", "and", "on", "in", "piece", "hand", "hands"}
MATCH_MIN = 0.5


def tokens(label):
    return {w for w in re.findall(r"[a-z]+", (label or "").lower()) if w not in STOP}


def similarity(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def load(clip_id):
    return json.loads((OUT / clip_id / "timeline.json").read_text())


def shift_log(clip_ids):
    """Every step across the shift's clips, in the given (chronological) order."""
    log = []
    for c in clip_ids:
        for s in load(c)["steps"]:
            log.append({"clip_id": c, "step_id": s["step_id"], "label": s["label"], "t_start": s["t_start"],
                        "cite": f"[{c}@{fmt_t(s['t_start'])}]"})
    return log


def already_done(label, clip_ids, before_clip=None, before_t=None):
    """Was something matching `label` already completed earlier in this shift?

    If before_clip/before_t are given, only entries strictly earlier than that point count, so asking
    mid-clip doesn't match the very thing about to be logged."""
    log = shift_log(clip_ids)
    if before_clip is not None and before_clip in clip_ids:
        cutoff = clip_ids.index(before_clip)
        log = [e for e in log if clip_ids.index(e["clip_id"]) < cutoff
               or (clip_ids.index(e["clip_id"]) == cutoff and (before_t is None or e["t_start"] < before_t))]
    matches = [e for e in log if similarity(label, e["label"]) >= MATCH_MIN]
    if not matches:
        return {"label": label, "already_done": False, "note": "Not found earlier in this shift."}
    first = matches[0]
    return {"label": label, "already_done": True, "first_seen": first,
            "note": f"Already completed at {first['cite']} ({first['label']})."}


if __name__ == "__main__":
    print(json.dumps(already_done(sys.argv[1], sys.argv[2:]), indent=1))
