"""AI-generated Shift Summary (USP 15): the end-of-shift report a supervisor would otherwise have to
assemble by hand, built entirely from numbers Kairo already measured this shift -- no invented
metric. Sections that need a capability the site hasn't configured (an SOP template for compliance,
or unsafe zones for safety) say so rather than reporting zero as if it were a measurement.

Usage: python events/shift_summary.py <clip_id> [<clip_id> ...]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import insights  # noqa: E402
import collab_score  # noqa: E402
import safety  # noqa: E402
import root_cause  # noqa: E402
from proficiency import _tl  # noqa: E402


def summarize(clip_ids, shift_hours=8.0, sop_results=None):
    """sop_results: optional list of events.sop.check(...) results, one per clip an SOP template
    exists for (USP 7). Omit it if no SOP template has been configured for this shift."""
    report = insights.analyse(clip_ids, shift_hours)
    collab = collab_score.shift_score(clip_ids)
    risk_rows = [safety.predict(c) for c in clip_ids]
    forecasts = sum(len(r["forecasts"]) for r in risk_rows)
    causes = root_cause.analyse(clip_ids)
    durations = [_tl(c)["duration_s"] for c in clip_ids]

    deviations = sum(1 for r in (sop_results or []) if not r["compliant"]) if sop_results is not None else None
    most_common_mistake = None
    if report["friction"]:
        worst_type, worst = max(report["friction"].items(), key=lambda kv: kv[1]["seconds"])
        if worst["count"]:
            most_common_mistake = {"type": worst_type, "count": worst["count"], "seconds": worst["seconds"]}

    fastest = min(clip_ids, key=lambda c: _tl(c)["duration_s"]) if clip_ids else None
    top_rec = report["recommendations"][0] if report["recommendations"] else None

    summary = {
        "clips": clip_ids, "assemblies": len(clip_ids),
        "quality_deviations": deviations,
        "quality_deviations_note": None if sop_results is not None else
            "No SOP template supplied for these clips; run events/sop.check() per clip to measure this.",
        "conversations": collab["total_collaboration_events"],
        "probable_safety_events": forecasts,
        "safety_note": None if any(r["configured"] for r in risk_rows) else
            "No unsafe zone configured for these stations; safety events cannot be measured yet.",
        "average_assembly_time_s": round(sum(durations) / len(durations), 1) if durations else None,
        "fastest_clip": fastest,
        "most_common_friction": most_common_mistake,
        "root_cause_findings": causes[:3],
        "top_recommendation": top_rec["title"] if top_rec else None,
        "lost_min_per_shift": report["lost_min_per_shift"],
        "headline": report["headline"],
    }
    lines = [f"Today's shift: {summary['assemblies']} clips processed, "
             f"{summary['average_assembly_time_s']}s average active work time."]
    if summary["quality_deviations"] is not None:
        lines.append(f"{summary['quality_deviations']} quality/SOP deviations.")
    lines.append(f"{summary['conversations']} collaboration events.")
    if summary["probable_safety_events"]:
        lines.append(f"{summary['probable_safety_events']} probable safety events flagged.")
    if most_common_mistake:
        lines.append(f"Most common friction: {most_common_mistake['type']} "
                     f"({most_common_mistake['count']}x, {most_common_mistake['seconds']:.0f}s total).")
    if top_rec:
        lines.append(f"Suggestion for tomorrow: {top_rec['title']}.")
    summary["narrative"] = " ".join(lines)
    return summary


if __name__ == "__main__":
    print(json.dumps(summarize(sys.argv[1:]), indent=1))
