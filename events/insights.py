"""Insights + layout recommendations over one or more clip timelines (a 'shift').

Turns friction into minutes per shift, with evidence timestamps, so the output reads like a
process engineer's recommendation rather than a dashboard.

Usage:
    python events/insights.py MTL-SGF00106-021 MTL-SGF00106-023 [--shift-hours 8]
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"

# fraction of each friction type we believe a fix can remove (conservative, stated on screen)
RECOVERABLE = {"search": 0.6, "transit": 0.4, "idle": 0.3, "hesitation": 0.5, "extra_reach": 0.3}


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
        for s in tl["steps"]:
            steps.append({**s, "clip_id": tl["clip_id"]})

    scale = shift_hours * 3600 / max(observed, 1e-6)  # extrapolation factor to one shift
    breakdown = {k: round(100 * v / observed, 1) for k, v in state_time.items()}
    lost_s = sum(ev_time[k] for k in RECOVERABLE)
    recoverable_s = sum(ev_time[k] * RECOVERABLE[k] for k in RECOVERABLE)

    recs = []

    def rec(kind, title, detail, typ, saving_s):
        ev = sorted(evidence[typ], key=lambda x: -x["dur"])[:5]
        recs.append({"kind": kind, "title": title, "detail": detail, "friction_type": typ,
                     "saving_min_per_shift": round(saving_s * scale / 60, 1),
                     "cycle_time_reduction_pct": round(100 * saving_s / max(observed, 1e-6), 1),
                     "evidence": ev, "support": f"{ev_count[typ]} events in {observed / 60:.1f} min observed"})

    if ev_count["search"]:
        side = search_dirs.most_common(1)[0][0] if search_dirs else None
        where = (f"Most searches turned the head to the {side} ({search_dirs[side]}/{ev_count['search']}), "
                 f"so frequently used tools sit outside the primary work zone. ") if side else ""
        rec("layout", "Stage frequently used tools in the front work zone",
            where + f"Searching cost {ev_time['search']:.0f}s ({ev_count['search']} times, "
                    f"avg {ev_time['search'] / ev_count['search']:.1f}s). A fixed tool cart / shadow board "
                    f"within arm's reach in front of the work piece removes most of it.",
            "search", ev_time["search"] * RECOVERABLE["search"])
    if ev_count["transit"]:
        rec("flow", "Kit materials at the station before each build",
            f"The worker left the work area {ev_count['transit']} times for {ev_time['transit']:.0f}s in total "
            f"(avg {ev_time['transit'] / ev_count['transit']:.1f}s). Pre-cut parts and fasteners delivered on a "
            f"kit trolley cut walking.",
            "transit", ev_time["transit"] * RECOVERABLE["transit"])
    if ev_count["idle"]:
        rec("flow", "Remove waiting time",
            f"{ev_count['idle']} idle periods ({ev_time['idle']:.0f}s) with hands out of view and head still: "
            f"usually waiting for material, a machine, or instructions.",
            "idle", ev_time["idle"] * RECOVERABLE["idle"])
    if ev_count["hesitation"]:
        rec("method", "Add a jig or visual guide where hands hesitate",
            f"{ev_count['hesitation']} hesitations ({ev_time['hesitation']:.0f}s): the hand stalls mid-task, "
            f"typical of alignment or positioning without a reference stop.",
            "hesitation", ev_time["hesitation"] * RECOVERABLE["hesitation"])
    if ev_count["extra_reach"]:
        rec("layout", "Shorten reach paths",
            f"{ev_count['extra_reach']} movements took a path over 3x the straight line: parts or tools "
            f"are placed awkwardly relative to the work piece.",
            "extra_reach", ev_time["extra_reach"] * RECOVERABLE["extra_reach"])
    recs.sort(key=lambda r: -r["saving_min_per_shift"])

    top = recs[0] if recs else None
    headline = None
    if top:
        e = top["evidence"][0] if top["evidence"] else None
        headline = (f"Based on {observed / 60:.1f} min of footage, \"{top['title'].lower()}\" could cut cycle "
                    f"time by about {top['cycle_time_reduction_pct']}%, saving ~{top['saving_min_per_shift']} min "
                    f"per {shift_hours:g}h shift. Supported by {top['support']}"
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
        "assumptions": {"recoverable_fraction": RECOVERABLE,
                        "note": "Shift figures are linear extrapolations from the observed footage."},
    }
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
