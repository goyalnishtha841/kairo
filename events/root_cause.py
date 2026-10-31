"""LLM Root Cause Analysis (USP 18): don't stop at "defect detected" -- suggest the mechanical reason
and a fix, grounded in the same evidence events/recommend.py already cites.

A deterministic rules layer runs first (always available, explainable, matches every other detector
in this stack) and maps a clustered friction pattern to a plausible root cause. ai/copilot.py can ask
an LLM to phrase that same evidence as a sentence, but the mapping itself -- and the evidence it is
grounded in -- never comes from the LLM, matching the project's "the LLM never invents a number" rule.

Usage: python events/root_cause.py <clip_id> [<clip_id> ...]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from insights import fmt_t, load  # noqa: E402

# pattern -> (friction types whose clustering within one step triggers it, root cause, recommended fix)
PATTERNS = [
    {"name": "loose_fixture", "types": ("reattempt", "extra_reach"), "min_events": 3,
     "root_cause": "Repeated tool/part repositioning around the same spot is consistent with a loose or "
                    "missing fixture, not a one-off mistake.",
     "fix": "Inspect and recalibrate (or add) the fixture/jig that should be holding the part still."},
    {"name": "missing_tool_station", "types": ("search",), "min_events": 4,
     "root_cause": "Frequent, repeated searching for the same kind of tool suggests the tool isn't kept at "
                    "the station, or there aren't enough of them.",
     "fix": "Add a dedicated holder for that tool within arm's reach, or stock a second one."},
    {"name": "unclear_reference", "types": ("hesitation",), "min_events": 4,
     "root_cause": "Frequent hesitation before placing/aligning suggests there is no clear visual reference "
                    "for the correct position.",
     "fix": "Add a jig, stop or marked position so the correct placement is unambiguous."},
]


def analyse(clip_ids):
    """Group evidence per step and match the counts against PATTERNS."""
    findings = []
    for c in clip_ids:
        tl = load(c)
        by_step = {}
        for e in tl["events"]:
            if e["step_id"] is not None:
                by_step.setdefault(e["step_id"], []).append(e)
        for step_id, evs in by_step.items():
            counts = {}
            for e in evs:
                counts[e["type"]] = counts.get(e["type"], 0) + 1
            for pat in PATTERNS:
                n = sum(counts.get(t, 0) for t in pat["types"])
                if n >= pat["min_events"]:
                    ev_cites = [f"[{c}@{fmt_t(e['t_start'])}]" for e in evs if e["type"] in pat["types"]][:3]
                    label = next((s["label"] for s in tl["steps"] if s["step_id"] == step_id), f"step {step_id}")
                    findings.append({"clip_id": c, "step_id": step_id, "step_label": label,
                                      "pattern": pat["name"], "event_count": n, "root_cause": pat["root_cause"],
                                      "fix": pat["fix"], "evidence": ev_cites})
    findings.sort(key=lambda f: -f["event_count"])
    return findings


if __name__ == "__main__":
    print(json.dumps(analyse(sys.argv[1:]), indent=1))
