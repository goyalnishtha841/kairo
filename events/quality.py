"""Smart Quality Score: a 0-100 score for how a task was done, with a reason behind every point.

Instead of "task completed", each recording and each of its steps gets a checklist:

    sequence   steps in the reference SOP's order (needs a reference recording: the station's SOP)
    tools      the same tools as the reference for matched steps (needs captioned steps)
    time       step durations vs the station's typical duration for the same kind of step
    movement   extra reaches and hand path efficiency vs the station baseline
    flow       idle and search time vs the station baseline

Each check earns points out of its weight; a check that cannot be measured is shown as n/a and the
score is re-normalised over the checks that could. Baselines are leave-one-out medians over the other
recordings of the same station. Steps cut off by the start or end of a recording are not timed.

Usage: python events/quality.py MTL-SGF00106-023 [--ref MTL-SGF00106-021]
"""
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare  # noqa: E402
import proficiency as P  # noqa: E402
from insights import fmt_t  # noqa: E402

WEIGHTS = {"sequence": 25, "tools": 15, "time": 25, "movement": 20, "flow": 15}
OK_AT, BAD_AT = 1.1, 2.0     # ratio vs baseline: full points up to 1.1x, none from 2x
FLOORS = {"extra_reach_per_min": 0.5, "flow_s_per_min": 3.0}   # baselines near 0 should not explode ratios
MIN_PEERS = 3                # same-kind steps needed for a duration baseline
EDGE_S = 0.5                 # steps this close to the clip's start or end are truncated
FLOW = ("idle", "search", "transit")
NOTE = "Scores how the task was done in this recording against the station's own baseline, not a person."


def _tl(clip_id):
    return json.loads((OUT / clip_id / "timeline.json").read_text())


def _cite(clip_id, t):
    return f"[{clip_id}@{fmt_t(t)}]"


def ratio_points(ratio):
    """1.0 up to OK_AT x baseline, falling linearly to 0 at BAD_AT x."""
    return max(0.0, min(1.0, (BAD_AT - ratio) / (BAD_AT - OK_AT)))


def status(frac):
    return "ok" if frac >= 0.85 else "warn" if frac >= 0.5 else "fail"


def _peers(clip_id):
    st = P.station_of(clip_id)
    return [c for c in P._all_clips() if P.station_of(c) == st and c != clip_id]


def _rate(tl, types):
    mins = max(tl["duration_s"] / 60, 1e-6)
    return sum(e["t_end"] - e["t_start"] for e in tl["events"] if e["type"] in types) / mins


def _count_rate(tl, typ):
    return sum(1 for e in tl["events"] if e["type"] == typ) / max(tl["duration_s"] / 60, 1e-6)


def timed_steps(tl):
    """Steps fully inside the recording (not cut off by its start or end)."""
    return [s for s in tl["steps"] if s["t_start"] > EDGE_S and s["t_end"] < tl["duration_s"] - EDGE_S]


def step_baselines(clip_id, cache):
    """Median duration per step kind (label) over the station's other recordings."""
    by = {}
    for c in _peers(clip_id):
        for s in timed_steps(cache.setdefault(("tl", c), _tl(c))):
            by.setdefault(s["label"], []).append(s["duration_s"])
    return {k: statistics.median(v) for k, v in by.items() if len(v) >= MIN_PEERS}


def _median_peer(clip_id, cache, fn):
    vals = [fn(cache.setdefault(("tl", c), _tl(c)), c) for c in _peers(clip_id)]
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


# ---------------------------------------------------------------- checks
def check_sequence(cmp):
    if cmp is None:
        return {"status": "na", "reason": "No reference SOP chosen for this station, so the order of steps is not checked."}
    c = cmp["counts"]
    frac = cmp["adherence_pct"] / 100
    issues = [f for f in cmp["findings"] if f.startswith(("Missing", "Out of order", "Extra"))]
    if c["missing"] == c["out_of_order"] == c["extra"] == 0:
        reason = f"Correct sequence: all {sum(c.values())} reference steps in order."
    else:
        reason = (f"Sequence {cmp['adherence_pct']}% of the reference: {c['missing']} missing, "
                  f"{c['out_of_order']} out of order, {c['extra']} extra.")
    return {"frac": frac, "reason": reason, "details": issues[:4]}


def check_tools(cmp):
    if cmp is None:
        return {"status": "na", "reason": "Needs a reference SOP to know which tools each step should use."}
    pairs = [x for x in cmp["rows"] if x.get("ref") and x.get("target") and x["status"] != "extra"]
    known = [x for x in pairs if x["ref"].get("tool") and x["target"].get("tool")]
    if not known:
        return {"status": "na", "reason": "Tool names are not available yet (steps are not captioned; run "
                                          "python ai/recaption.py)."}
    same = [x for x in known if x["ref"]["tool"].lower() == x["target"]["tool"].lower()]
    wrong = [x for x in known if x not in same]
    reason = ("Correct tools on every matched step." if not wrong else
              f"Tools match on {len(same)} of {len(known)} steps.")
    details = [f"\"{x['ref']['label']}\": {x['target']['tool']} instead of {x['ref']['tool']} "
               f"{_cite(cmp['target'], x['target']['t_start'])}" for x in wrong[:3]]
    return {"frac": len(same) / len(known), "reason": reason, "details": details}


def check_time(clip_id, tl, base):
    rows = [(s, base[s["label"]]) for s in timed_steps(tl) if s["label"] in base]
    if not rows:
        return {"status": "na", "reason": "No complete step here has enough same-kind steps at this station to time it."}
    actual, typical = sum(s["duration_s"] for s, _ in rows), sum(b for _, b in rows)
    r = actual / max(typical, 1e-6)
    slow = sorted(((s["duration_s"] / b, s, b) for s, b in rows if s["duration_s"] / b > OK_AT), key=lambda x: -x[0])
    n = f"{len(rows)} timed step{'s' if len(rows) != 1 else ''}"
    if ratio_points(r) >= 0.85:
        reason = f"On time: {actual:.0f}s across {n} vs a typical {typical:.0f}s."
    else:
        reason = f"Took longer than baseline: {actual:.0f}s vs a typical {typical:.0f}s ({r:.1f}x) across {n}."
    details = [f"\"{s['label']}\" {s['duration_s']:.0f}s vs typical {b:.0f}s {_cite(clip_id, s['t_start'])}"
               for _, s, b in slow[:3]]
    return {"frac": ratio_points(r), "reason": reason, "details": details, "ratio": round(r, 2)}


def check_movement(clip_id, tl, cache):
    xr = _count_rate(tl, "extra_reach")
    base_xr = _median_peer(clip_id, cache, lambda t, c: _count_rate(t, "extra_reach"))
    pe = cache.setdefault(("m", clip_id), P.metrics(clip_id)).get("path_efficiency")
    base_pe = _median_peer(clip_id, cache, lambda t, c: cache.setdefault(("m", c), P.metrics(c)).get("path_efficiency"))
    if base_xr is None:
        return {"status": "na", "reason": "No other recordings of this station to compare movement with."}
    r = xr / max(base_xr, FLOORS["extra_reach_per_min"])
    if pe and base_pe:   # a less direct hand path counts as extra movement too
        r = max(r, base_pe / max(pe, 1e-6))
    evs = sorted((e for e in tl["events"] if e["type"] == "extra_reach"), key=lambda e: e["t_start"])
    if ratio_points(r) >= 0.85:
        reason = f"Economical movement: {xr:.1f} extra reaches/min vs {base_xr:.1f} at this station"
    else:
        reason = f"Extra unnecessary movement: {xr:.1f} extra reaches/min vs {base_xr:.1f} at this station"
    reason += f", hand path {pe:.0f}% direct vs {base_pe:.0f}%." if pe and base_pe else "."
    details = [f"{e['note']} {_cite(clip_id, e['t_start'])}" for e in evs[:3]] if ratio_points(r) < 0.85 else []
    return {"frac": ratio_points(r), "reason": reason, "details": details, "ratio": round(r, 2)}


def check_flow(clip_id, tl, cache):
    fl = _rate(tl, FLOW)
    base = _median_peer(clip_id, cache, lambda t, c: _rate(t, FLOW))
    if base is None:
        return {"status": "na", "reason": "No other recordings of this station to compare flow with."}
    r = fl / max(base, FLOORS["flow_s_per_min"])
    evs = sorted((e for e in tl["events"] if e["type"] in FLOW), key=lambda e: e["t_start"] - e["t_end"])
    reason = (f"Smooth flow: {fl:.1f}s/min idle or searching vs {base:.1f} at this station." if ratio_points(r) >= 0.85 else
              f"Interrupted flow: {fl:.1f}s/min idle or searching vs {base:.1f} at this station.")
    details = [f"{e['type']} {e['t_end'] - e['t_start']:.0f}s {_cite(clip_id, e['t_start'])}" for e in evs[:3]] \
        if ratio_points(r) < 0.85 else []
    return {"frac": ratio_points(r), "reason": reason, "details": details, "ratio": round(r, 2)}


def _finish(checks):
    out, earned, avail = [], 0.0, 0
    for name, c in checks.items():
        w = WEIGHTS[name]
        if c.get("status") == "na":
            out.append({"check": name, "status": "na", "weight": w, "points": None, "reason": c["reason"], "details": []})
            continue
        pts = w * c["frac"]
        earned, avail = earned + pts, avail + w
        out.append({"check": name, "status": status(c["frac"]), "weight": w, "points": round(pts, 1),
                    "reason": c["reason"], "details": c.get("details", [])})
    return (round(100 * earned / avail) if avail else None), out, avail


# ---------------------------------------------------------------- per step
def step_quality(clip_id, tl, base, cmp):
    seq = {}
    if cmp:
        for x in cmp["rows"]:
            if x.get("target"):
                seq[x["target"]["step_id"]] = x["status"]
    timed = {s["step_id"] for s in timed_steps(tl)}
    out = []
    for s in tl["steps"]:
        inside = [e for e in tl["events"] if s["t_start"] <= e["t_start"] <= s["t_end"]]
        reasons, fracs = [], []
        if s["step_id"] in timed and s["label"] in base:
            r = s["duration_s"] / base[s["label"]]
            fracs.append(ratio_points(r))
            reasons.append({"status": status(fracs[-1]),
                            "text": f"{s['duration_s']:.0f}s vs typical {base[s['label']]:.0f}s"
                            + (" (took longer than baseline)" if fracs[-1] < 0.85 else "")})
        elif s["step_id"] in timed:
            reasons.append({"status": "na", "text": f"Not timed: fewer than {MIN_PEERS} steps of this kind at the station"})
        xr = [e for e in inside if e["type"] == "extra_reach"]
        fracs.append(1.0 if not xr else 0.6 if len(xr) == 1 else 0.3)
        reasons.append({"status": status(fracs[-1]), "text": "No extra movement" if not xr else
                        f"{len(xr)} extra reach{'es' if len(xr) > 1 else ''} {_cite(clip_id, xr[0]['t_start'])}"})
        fl = [e for e in inside if e["type"] in FLOW]
        fracs.append(1.0 if not fl else 0.6 if len(fl) == 1 else 0.3)
        reasons.append({"status": status(fracs[-1]), "text": "No idle or searching" if not fl else
                        f"{len(fl)} idle/search spell{'s' if len(fl) > 1 else ''} {_cite(clip_id, fl[0]['t_start'])}"})
        st = seq.get(s["step_id"])
        if st:
            ok = st in ("match", "slower", "faster")
            fracs.append(1.0 if ok else 0.3)
            reasons.append({"status": "ok" if ok else "fail",
                            "text": "In the reference sequence" if ok else
                            {"out_of_order": "Out of order vs the reference", "extra": "Not in the reference"}.get(st, st)})
        out.append({"step_id": s["step_id"], "label": s["label"], "tool": s.get("tool"),
                    "t_start": s["t_start"], "duration_s": s["duration_s"],
                    "score": round(100 * sum(fracs) / len(fracs)), "reasons": reasons,
                    "timed": s["step_id"] in timed})
    return out


def score(clip_id, ref=None, cache=None):
    cache = cache if cache is not None else {}
    tl = cache.setdefault(("tl", clip_id), _tl(clip_id))
    cmp = compare.compare(ref, clip_id) if ref and ref != clip_id else None
    base = step_baselines(clip_id, cache)
    checks = {"sequence": check_sequence(cmp), "tools": check_tools(cmp),
              "time": check_time(clip_id, tl, base), "movement": check_movement(clip_id, tl, cache),
              "flow": check_flow(clip_id, tl, cache)}
    total, rows, avail = _finish(checks)
    peers = _peers(clip_id)
    return {
        "clip_id": clip_id, "station": P.station_of(clip_id), "reference": cmp and ref,
        "score": total, "grade": None if total is None else "Good" if total >= 85 else "Fair" if total >= 60 else "Poor",
        "checks": rows, "measured_weight": avail,
        "steps": step_quality(clip_id, tl, base, cmp),
        "baseline_recordings": len(peers),
        "reliability": "high" if len(peers) >= 5 else "medium" if len(peers) >= 3 else "low",
        "note": NOTE,
        "method": (f"Weights {', '.join(f'{k} {v}' for k, v in WEIGHTS.items())}. Each check earns full points up to "
                   f"{OK_AT}x the station's leave-one-out median and none from {BAD_AT}x; n/a checks are left out and "
                   f"the score is re-normalised over {avail} measured points."),
    }


def station_scores(station, ref=None, cache=None):
    cache = cache if cache is not None else {}
    return [{"clip_id": c, "score": score(c, ref, cache)["score"]}
            for c in P._all_clips() if P.station_of(c) == station]


if __name__ == "__main__":
    args = sys.argv[1:]
    ref = args[args.index("--ref") + 1] if "--ref" in args else None
    clips = [a for a in args if not a.startswith("--") and a != ref] or P._all_clips()
    cache = {}
    for c in clips:
        r = score(c, ref, cache)
        print(f"\n{c}: {r['score']}/100 ({r['grade']}), {r['baseline_recordings']} peers")
        for ch in r["checks"]:
            mark = {"ok": "✓", "warn": "⚠", "fail": "✗", "na": "–"}[ch["status"]]
            print(f"  {mark} {ch['check']:9s} {ch['points'] if ch['points'] is not None else 'n/a':>5} / {ch['weight']}  {ch['reason']}")
