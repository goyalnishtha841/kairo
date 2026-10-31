"""Multi-worker Collaboration Score (USP 14): aggregate the collaboration events
events/collaboration.py already detects into numbers a manager can act on: how often help happens,
how long work waits for it, how dependent the workflow is on another person showing up, and how much
of it looks like real back-and-forth communication.

All four numbers come straight out of the per-event signal shares collaboration.py already stores
(evidence.signal_share / evidence.work_resumes); nothing new is inferred about who the other person
is. Kairo has no worker identity (see docs/STRATEGY.md's privacy stance), so this scores a *clip* --
"this recording waited on another person this much" -- never a person.

Usage: python events/collab_score.py <clip_id> [<clip_id> ...]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from insights import fmt_t  # noqa: E402

COLLAB_TYPES = ("collaboration", "possible_collaboration")


def load(clip_id):
    return json.loads((OUT / clip_id / "timeline.json").read_text())


def score(clip_id):
    tl = load(clip_id)
    evs = [e for e in tl["events"] if e["type"] in COLLAB_TYPES]
    mins = max(tl["duration_s"] / 60, 1e-6)
    if not evs:
        return {"clip_id": clip_id, "events": 0, "help_frequency_per_hour": 0.0, "waiting_s": 0.0,
                "dependency_pct": 0.0, "communication_pct": 0.0, "evidence": [],
                "note": "No high-confidence collaboration events in this clip."}
    waiting_s = sum(e["t_end"] - e["t_start"] for e in evs
                     if e.get("evidence", {}).get("signal_share", {}).get("paused", 0) >= 0.5)
    speech_shares = [e["evidence"]["signal_share"].get("speech", 0) for e in evs if e.get("evidence")]
    dependency = sum(1 for e in evs if e.get("evidence", {}).get("work_resumes")) / len(evs)
    return {
        "clip_id": clip_id, "events": len(evs),
        "help_frequency_per_hour": round(len(evs) / mins * 60, 1),
        "waiting_s": round(waiting_s, 1),
        "dependency_pct": round(100 * dependency, 1),
        "communication_pct": round(100 * (sum(speech_shares) / len(speech_shares)), 1) if speech_shares else 0.0,
        "evidence": [f"[{clip_id}@{fmt_t(e['t_start'])}]" for e in evs[:5]],
        "note": "Dependency = share of collaboration events after which work resumed (the workflow was "
                "waiting on that person). Communication = mean speech-activity share during those events "
                "(activity only, never content).",
    }


def shift_score(clip_ids):
    rows = [score(c) for c in clip_ids]
    total_evs = sum(r["events"] for r in rows)
    busiest = max(rows, key=lambda r: r["waiting_s"]) if rows and total_evs else None
    return {
        "clips": clip_ids, "total_collaboration_events": total_evs,
        "avg_help_frequency_per_hour": round(sum(r["help_frequency_per_hour"] for r in rows) / max(len(rows), 1), 1),
        "total_waiting_s": round(sum(r["waiting_s"] for r in rows), 1),
        "by_clip": rows,
        "clip_with_most_waiting": busiest["clip_id"] if busiest else None,
        "note": "No worker identity is tracked, so this never ranks a person -- only which recording's "
                "workflow waited on another person the most.",
    }


if __name__ == "__main__":
    print(json.dumps(shift_score(sys.argv[1:]), indent=1))
