"""Insights + layout recommendations over one or more clip timelines (a 'shift').

Turns friction into minutes per shift, with evidence timestamps, so the output reads like a
process engineer's recommendation rather than a dashboard.

Usage:
    python events/insights.py MTL-SGF00106-021 MTL-SGF00106-023 [--shift-hours 8]
"""
import argparse
import json
from collections import Counter, defaultdict
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import recommend  # noqa: E402

RECOVERABLE = C.RECOVERABLE  # share of each friction type a fix can remove (stated on screen)

# USP 9: human-readable reasons for the "why did productivity drop" question
REASON_LABEL = {"search": "searching for tool", "transit": "walking away / fetching",
                "idle": "idle / waiting (or talking)", "hesitation": "hesitation",
                "extra_reach": "extra reach", "reattempt": "repeated movement (unnecessary corrections)"}


def reasons(report):
    """Friction seconds, ranked -- the breakdown behind "productivity dropped to 72%"."""
    fr = report["friction"]
    total = sum(v["seconds"] for v in fr.values()) or 1.0
    rows = [{"type": k, "label": REASON_LABEL.get(k, k), "seconds": round(v["seconds"], 1), "count": v["count"],
             "pct_of_lost": round(100 * v["seconds"] / total, 1)} for k, v in fr.items() if v["seconds"] > 0]
    rows.sort(key=lambda r: -r["seconds"])
    return rows


def load(clip_id):
    return json.loads((OUT / clip_id / "timeline.json").read_text())


def fmt_t(s):
    return f"{int(s // 60):02d}:{int(s % 60):02d}"


def analyse(clip_ids, shift_hours=8.0):
    tls = [load(c) for c in clip_ids]
    observed = sum(tl["duration_s"] for tl in tls)
    state_time = Counter()
    ev_time, ev_count = Counter(), Counter()
    evidence = defaultdict(list)
    search_dirs = Counter()
    steps = []
    collab = []

    for tl in tls:
        for s in tl["states"]:
            state_time[s["state"]] += s["t_end"] - s["t_start"]
        for e in tl["events"]:
            d = e["t_end"] - e["t_start"]
            ev_time[e["type"]] += d
            ev_count[e["type"]] += 1
            evidence[e["type"]].append({"clip_id": tl["clip_id"], "t": e["t_start"], "dur": round(d, 1),
                                        "id": e["id"], "note": e["note"]})
            if e["type"] == "search" and e.get("zone"):
                search_dirs[e["zone"]] += 1
            if e["type"] in ("collaboration", "possible_collaboration"):
                collab.append({"clip_id": tl["clip_id"], "t": e["t_start"], "dur": round(d, 1), "type": e["type"],
                               "confidence": e.get("confidence"), "note": e["note"]})
        for s in tl["steps"]:
            steps.append({**s, "clip_id": tl["clip_id"]})

    scale = shift_hours * 3600 / max(observed, 1e-6)  # extrapolation factor to one shift
    breakdown = {k: round(100 * v / observed, 1) for k, v in state_time.items()}
    lost_s = sum(ev_time[k] for k in RECOVERABLE)
    recoverable_s = sum(ev_time[k] * RECOVERABLE[k] for k in RECOVERABLE)

    recs = recommend.build(evidence, observed, len(clip_ids), dict(search_dirs), shift_hours)

    top = recs[0] if recs else None
    headline = None
    if top:
        e = top["evidence"][0] if top["evidence"] else None
        headline = (f"Based on {observed / 60:.1f} min of footage, \"{top['title'].lower()}\" could cut cycle "
                    f"time by about {top['cycle_time_reduction_pct']}%, saving ~{top['saving_min_per_shift']} min "
                    f"per {shift_hours:g}h shift (confidence {round(100 * top['confidence'])}%). "
                    f"Supported by {top['support']}"
                    + (f", e.g. {e['clip_id']} at {fmt_t(e['t'])}." if e else "."))

    report = {
        "clips": clip_ids,
        "observed_min": round(observed / 60, 2),
        "shift_hours": shift_hours,
        "extrapolated": True,
        "breakdown_pct": breakdown,
        "friction": {k: {"count": ev_count[k], "seconds": round(ev_time[k], 1)} for k in RECOVERABLE},
        "lost_min_per_shift": round(lost_s * scale / 60, 1),
        "recoverable_min_per_shift": round(recoverable_s * scale / 60, 1),
        "steps": len(steps),
        "avg_step_s": round(sum(s["duration_s"] for s in steps) / len(steps), 1) if steps else None,
        "longest_step": max(steps, key=lambda s: s["duration_s"]) if steps else None,
        "recommendations": recs,
        "search_directions": dict(search_dirs),
        "work_zones": {z: round(sum(s["duration_s"] for s in steps if s.get("zone") == z), 1)
                       for z in ("left", "center", "right")},
        "headline": headline,
        "roi_eur_per_year_total": sum(r["roi_eur_per_year"] for r in recs),
        "collaboration_events": collab,
        "lost_time_reasons": [],  # filled below, after `report` exists (reasons() reads report["friction"])
        "assumptions": {"recoverable_fraction": RECOVERABLE,
                        "labor_eur_per_hour": C.LABOR_EUR_PER_HOUR, "shifts_per_day": C.SHIFTS_PER_DAY,
                        "workdays_per_year": C.WORKDAYS_PER_YEAR,
                        "note": "Shift figures are linear extrapolations from the observed footage. "
                                "EUR per year = minutes per shift x labour rate x shifts per day x workdays."},
    }
    report["lost_time_reasons"] = reasons(report)
    if report["lost_time_reasons"]:
        parts = ", ".join(f"{r['seconds']:.0f}s {r['label']}" for r in report["lost_time_reasons"][:4])
        report["productivity_explanation"] = f"Lost time breakdown: {parts}."
    else:
        report["productivity_explanation"] = "No measurable friction in the selected clips."
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--shift-hours", type=float, default=8.0)
    a = ap.parse_args()
    r = analyse(a.clips, a.shift_hours)
    (OUT / "shift_report.json").write_text(json.dumps(r, indent=1))
    print(json.dumps({k: r[k] for k in ("observed_min", "breakdown_pct", "friction",
                                        "lost_min_per_shift", "headline")}, indent=1))
