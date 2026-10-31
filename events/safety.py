"""Safety Risk Predictor (USP 13): not just flag an unsafe reach, forecast the next one.

An "unsafe reach" is an extra_reach event (hand path much longer than the straight line -- an
uncontrolled, fast motion) into a zone a site operator has flagged as hazardous for that station
(events/config.py UNSAFE_ZONES). With no zones configured for a station, we detect nothing there: a
false "all safe" is worse than silence, but a fabricated danger zone is worse still.

The forecast is a frequency heuristic, not a trained model, and says so: if 2+ unsafe reaches
happened in the last RISK_WINDOW_S seconds, that rate is extrapolated (Poisson) to a probability of
another one in the next RISK_WINDOW_S seconds. Deliberately simple and explainable, matching the
project's "never show a confidence we can't explain" rule.

Usage: python events/safety.py <clip_id>
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
from insights import fmt_t  # noqa: E402
from proficiency import station_of  # noqa: E402

RISK_WINDOW_S = 30.0
RISK_MIN_EVENTS = 2


def load(clip_id):
    return json.loads((OUT / clip_id / "timeline.json").read_text())


def unsafe_zones_for(clip_id):
    return set(C.UNSAFE_ZONES.get(station_of(clip_id), []))


def unsafe_reaches(clip_id):
    zones = unsafe_zones_for(clip_id)
    if not zones:
        return []
    tl = load(clip_id)
    return [e for e in tl["events"] if e["type"] == "extra_reach" and e.get("zone") in zones]


def predict(clip_id):
    zones = unsafe_zones_for(clip_id)
    if not zones:
        return {"clip_id": clip_id, "configured": False,
                "note": f"No unsafe zone configured for station {station_of(clip_id)}; nothing to report.",
                "events": [], "forecasts": []}
    reaches = sorted(unsafe_reaches(clip_id), key=lambda e: e["t_start"])
    events_out = [{"t_start": e["t_start"], "zone": e["zone"], "note": e["note"],
                   "cite": f"[{clip_id}@{fmt_t(e['t_start'])}]"} for e in reaches]
    forecasts = []
    for i, e in enumerate(reaches):
        window = [r for r in reaches[:i + 1] if e["t_start"] - r["t_start"] <= RISK_WINDOW_S]
        if len(window) >= RISK_MIN_EVENTS:
            rate = len(window) / RISK_WINDOW_S
            p = round(min(0.95, 1 - math.exp(-rate * RISK_WINDOW_S)), 2)
            forecasts.append({"t": e["t_start"], "cite": f"[{clip_id}@{fmt_t(e['t_start'])}]",
                               "recent_count": len(window), "window_s": RISK_WINDOW_S,
                               "probability_next_window": p,
                               "note": f"{len(window)} unsafe reaches into zone '{e['zone']}' in the last "
                                       f"{RISK_WINDOW_S:.0f}s -> estimated {p * 100:.0f}% chance of another "
                                       f"in the next {RISK_WINDOW_S:.0f}s if this rate continues."})
    return {"clip_id": clip_id, "configured": True, "unsafe_zones": sorted(zones),
            "events": events_out, "forecasts": forecasts,
            "method": "Poisson-rate extrapolation from recent unsafe-reach frequency -- a heuristic, not a "
                      "trained model, shown with its formula so it's never an unexplained confidence number."}


if __name__ == "__main__":
    print(json.dumps(predict(sys.argv[1]), indent=1))
