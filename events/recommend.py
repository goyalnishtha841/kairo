"""Recommendation engine: every recommendation is an evidence record, not a sentence.

Each one carries: observation, evidence statistics, supporting timestamps, an evidence-based confidence
(with its formula), estimated minutes per shift, estimated EUR per year, and a simulation of the
timeline with the waste removed.
"""
import math
import statistics

import config as C

KIND = {"search": "layout", "transit": "flow", "idle": "flow", "hesitation": "method", "extra_reach": "layout"}
TITLE = {
    "search": "Stage frequently used tools in the front work zone",
    "transit": "Kit materials at the station before each build",
    "idle": "Remove waiting time",
    "hesitation": "Add a jig or visual guide where hands hesitate",
    "extra_reach": "Shorten reach paths",
}
ACTION = {
    "search": "Put a shadow board or tool cart within arm's reach in front of the work piece.",
    "transit": "Deliver pre-cut parts and fasteners on a kit trolley before each build.",
    "idle": "Check material supply and machine availability at these moments; pre-stage the next job.",
    "hesitation": "Add a reference stop, jig or marked position for the alignment steps.",
    "extra_reach": "Move parts and tools so the hand path is short and straight.",
}


def confidence(durations, n_clips_with, n_clips):
    """Evidence-based confidence in [0, 1]:
       0.5 * volume (1 - exp(-n/12): more events, more certain)
     + 0.3 * spread (share of clips where it happens: not a one-off)
     + 0.2 * consistency (1 / (1 + coefficient of variation of durations))."""
    n = len(durations)
    if n == 0:
        return 0.0
    volume = 1 - math.exp(-n / 12)
    spread = n_clips_with / max(n_clips, 1)
    cv = statistics.pstdev(durations) / max(statistics.mean(durations), 1e-6) if n > 1 else 1.0
    consistency = 1 / (1 + cv)
    return round(min(1.0, 0.5 * volume + 0.3 * spread + 0.2 * consistency), 2)


def roi_eur_per_year(min_per_shift):
    return round(min_per_shift / 60 * C.LABOR_EUR_PER_HOUR * C.SHIFTS_PER_DAY * C.WORKDAYS_PER_YEAR)


def observation(typ, n, total, mean, search_dirs):
    if typ == "search":
        side = max(search_dirs, key=search_dirs.get) if search_dirs else None
        where = f" Most searches turned the head to the {side} ({search_dirs[side]} of {n})." if side else ""
        return f"Hands leave the work and the head scans for tools {n} times, {mean:.1f}s on average.{where}"
    if typ == "transit":
        return f"The worker leaves the work area {n} times, {mean:.1f}s on average."
    if typ == "idle":
        return f"Hands are out of view with the head still {n} times, {mean:.1f}s on average (waiting or talking)."
    if typ == "hesitation":
        return f"The hand stalls mid-task {n} times, {mean:.1f}s on average, typical of alignment without a reference."
    return f"{n} hand movements took a path over 3x the straight line."


def build(evidence, observed_s, n_clips, search_dirs, shift_hours=None):
    """evidence: {type: [{clip_id, t, dur, id, note}, ...]} -> ranked recommendation records."""
    shift_s = (shift_hours or C.SHIFT_HOURS) * 3600
    scale = shift_s / max(observed_s, 1e-6)
    recs = []
    for typ, frac in C.RECOVERABLE.items():
        evs = evidence.get(typ, [])
        if not evs:
            continue
        durs = [e["dur"] for e in evs]
        total = sum(durs)
        saving_s = total * frac
        min_shift = round(saving_s * scale / 60, 1)
        clips_with = len({e["clip_id"] for e in evs})
        conf = confidence(durs, clips_with, n_clips)
        support = sorted(evs, key=lambda x: -x["dur"])[:5]
        recs.append({
            "kind": KIND[typ], "friction_type": typ, "title": TITLE[typ],
            "observation": observation(typ, len(evs), total, total / len(evs), search_dirs),
            "action": ACTION[typ],
            "detail": observation(typ, len(evs), total, total / len(evs), search_dirs) + " " + ACTION[typ],
            "evidence_stats": {"events": len(evs), "total_s": round(total, 1),
                               "mean_s": round(total / len(evs), 1), "median_s": round(statistics.median(durs), 1),
                               "clips": clips_with, "of_clips": n_clips},
            "confidence": conf,
            "confidence_method": "0.5 x evidence volume + 0.3 x spread across clips + 0.2 x consistency",
            "recoverable_share": frac,
            "saving_min_per_shift": min_shift,
            "roi_eur_per_year": roi_eur_per_year(min_shift),
            "cycle_time_reduction_pct": round(100 * saving_s / max(observed_s, 1e-6), 1),
            "evidence": support,
            "support": f"{len(evs)} events in {observed_s / 60:.1f} min observed, seen in {clips_with}/{n_clips} clips",
        })
    recs.sort(key=lambda r: -r["roi_eur_per_year"])
    return recs


def simulate(timeline, friction_type):
    """Timeline with the recoverable share of one friction type removed.

    Each event of that type is shortened by RECOVERABLE[type]; everything after it moves earlier.
    Returns before/after state lists and the seconds saved, for a before/after bar in the UI."""
    frac = C.RECOVERABLE.get(friction_type, 0)
    cuts = sorted((e["t_start"], (e["t_end"] - e["t_start"]) * frac)
                  for e in timeline["events"] if e["type"] == friction_type)

    def shift(t):
        # time removed before t (a cut starting before t removes up to its length)
        return sum(min(length, max(0.0, t - start)) for start, length in cuts)

    after = []
    for s in timeline["states"]:
        a, b = s["t_start"] - shift(s["t_start"]), s["t_end"] - shift(s["t_end"])
        if b - a > 0.05:
            after.append({"state": s["state"], "t_start": round(a, 2), "t_end": round(b, 2)})
    saved = round(sum(length for _, length in cuts), 1)
    return {"clip_id": timeline["clip_id"], "friction_type": friction_type, "recoverable_share": frac,
            "before": timeline["states"], "after": after,
            "duration_before": timeline["duration_s"], "duration_after": round(timeline["duration_s"] - saved, 1),
            "saved_s": saved}
