"""Behavior Drift Detection (USP 16) + Adaptive Baseline (USP 17).

USP 17 (adaptive): compare a recording with THIS STATION'S OWN recent history ("today vs
yesterday"), not with other workers -- fairer, and matches proficiency.py's "describe the workflow,
never the person" rule.

USP 16 (drift): if that change crosses DRIFT_PCT, report it and name which friction type grew the
most, mapped to a plausible (never asserted-as-fact) reason a manager should go check.

Usage: python events/baseline_drift.py <clip_id>
"""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from proficiency import _all_clips, _tl, metrics, station_of  # noqa: E402

DRIFT_PCT = 20.0  # a change this big in active work time is "significant", not noise
METRIC_TO_FRICTION = {"search_s_per_min": "search", "idle_s_per_min": "idle",
                       "hesitations_per_min": "hesitation"}
POSSIBLE_REASONS = {
    "search": "more time spent searching for tools or parts -> possibly a missing/moved item",
    "idle": "more idle time -> possibly waiting on material or a machine",
    "hesitation": "more hesitation -> possibly an unfamiliar product variant, or fatigue",
}


def active_work_s(clip_id):
    tl = _tl(clip_id)
    return sum(s["t_end"] - s["t_start"] for s in tl["states"] if s["state"] == "work")


def self_baseline(clip_id, history=2):
    """The N recordings of the same station immediately before this one, in processing order."""
    st = station_of(clip_id)
    series = sorted(set([c for c in _all_clips() if station_of(c) == st] + [clip_id]))
    i = series.index(clip_id)
    return series[max(0, i - history):i]


def adaptive_score(clip_id, history=2):
    """USP 17: compare this recording with its own recent history, not the station median."""
    prior = self_baseline(clip_id, history)
    today = active_work_s(clip_id)
    if not prior:
        return {"clip_id": clip_id, "prior_clips": [], "today_active_work_s": round(today, 1),
                "baseline_active_work_s": None, "change_pct": None,
                "headline": "No earlier recording of this station to compare with yet.",
                "method": "Compares active work time with the median of the previous recordings of the "
                          "SAME station (self baseline), not a cross-worker ranking."}
    base = statistics.median(active_work_s(c) for c in prior)
    change = round(100 * (base - today) / base, 1) if base else 0.0  # positive = faster today
    headline = (f"Productivity improved {change:.0f}% vs this station's own recent history." if change > 0 else
                f"Productivity dropped {abs(change):.0f}% vs this station's own recent history." if change < 0 else
                "No change vs this station's own recent history.")
    return {"clip_id": clip_id, "prior_clips": prior, "today_active_work_s": round(today, 1),
            "baseline_active_work_s": round(base, 1), "change_pct": change, "headline": headline,
            "method": "Compares active work time with the median of the previous recordings of the SAME "
                      "station (self baseline), not a cross-worker ranking."}


def drift(clip_id, history=2):
    """USP 16: flag a significant change and point at which friction type grew the most."""
    a = adaptive_score(clip_id, history)
    if a["change_pct"] is None or abs(a["change_pct"]) < DRIFT_PCT:
        return {**a, "drifted": False, "possible_reasons": []}
    m_today = metrics(clip_id)
    prior_metrics = [metrics(c) for c in a["prior_clips"]]
    grown = []
    for k, friction in METRIC_TO_FRICTION.items():
        vals = [pm[k] for pm in prior_metrics if pm.get(k) is not None]
        now = m_today.get(k)
        if not vals or now is None:
            continue
        base = statistics.median(vals)
        if base and now > base * 1.3:
            grown.append(friction)
    reasons = [POSSIBLE_REASONS[k] for k in grown]
    return {**a, "drifted": True,
            "headline": f"Behaviour deviates significantly from this station's recent history "
                        f"({a['change_pct']:+.0f}%).",
            "grown_friction": grown, "possible_reasons": reasons or
            ["No single friction type stands out; worth a manual check (fatigue, unfamiliar product, "
             "missing material)."]}


if __name__ == "__main__":
    print(json.dumps(drift(sys.argv[1]), indent=1))
