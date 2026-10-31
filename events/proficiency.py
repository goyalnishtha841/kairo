"""Workflow Proficiency Engine: compare one recording's WORKFLOW with its station's baseline.

It never classifies a person. For each recording we measure workflow metrics from the timeline,
build a robust baseline from the other recordings of the same station (leave-one-out median and
MAD), turn deviations into 0-100 sub-scores, and explain every point with numbers and timestamps.

Usage: python events/proficiency.py MTL-SGF00106-023
"""
import json
import statistics
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
from insights import fmt_t  # noqa: E402

# name, unit, higher_is_better, label
METRICS = [
    ("hands_on_pct", "%", True, "Hands-on work"),
    ("search_s_per_min", "s/min", False, "Searching"),
    ("idle_s_per_min", "s/min", False, "Idle / waiting"),
    ("hesitations_per_min", "/min", False, "Hesitations"),
    ("path_efficiency", "%", True, "Hand path efficiency"),
    ("interruptions_per_min", "/min", False, "Interruptions"),
]
# Smallest difference that matters in practice: max(absolute floor, 25% of the baseline value).
# Stops near-identical stations (MAD ~ 0) from turning a 2% gap into a big penalty.
SCALE_FLOOR = {"hands_on_pct": 8.0, "search_s_per_min": 2.0, "idle_s_per_min": 3.0,
               "hesitations_per_min": 0.5, "path_efficiency": 5.0, "interruptions_per_min": 1.5}
REL_FLOOR = 0.25


def station_of(clip_id):
    return clip_id.rsplit("-", 1)[0]


def _tl(clip_id):
    return json.loads((OUT / clip_id / "timeline.json").read_text())


def path_efficiency(clip_id):
    """Mean straight-line / path-length ratio of hand movements (100% = perfectly direct)."""
    p = OUT / clip_id / "hands.json"
    if not p.exists():
        return None
    frames = json.loads(p.read_text())["frames"]
    ratios = []
    for hid in ("L", "R"):
        run = []
        for f in frames + [{"hands": []}]:
            hd = next((h for h in f["hands"] if h["id"] == hid), None)
            if hd is not None:
                run.append(np.array(hd["lm"])[[0, 5, 9, 13, 17], :2].mean(0))
                continue
            if len(run) >= 6:
                pts = np.array(run)
                step = np.linalg.norm(np.diff(pts, axis=0), axis=1)
                moving = step > 0.004
                # split into movements on stillness and score each
                i = 0
                while i < len(moving):
                    if moving[i]:
                        j = i
                        while j + 1 < len(moving) and moving[j + 1]:
                            j += 1
                        seg = pts[i:j + 2]
                        path = step[i:j + 1].sum()
                        disp = np.linalg.norm(seg[-1] - seg[0])
                        if path > 0.05:
                            ratios.append(min(1.0, disp / path))
                        i = j + 1
                    else:
                        i += 1
            run = []
    return round(100 * float(np.mean(ratios)), 1) if ratios else None


def metrics(clip_id):
    """Workflow metrics for one recording, cached on disk until its timeline or hand tracks change."""
    d = OUT / clip_id
    stamp = [round((d / f).stat().st_mtime, 3) for f in ("timeline.json", "hands.json") if (d / f).exists()]
    cache_file = d / "proficiency_metrics.json"
    if cache_file.exists():
        cached = json.loads(cache_file.read_text())
        if cached.get("stamp") == stamp:
            return cached["metrics"]
    m = _compute_metrics(clip_id)
    cache_file.write_text(json.dumps({"stamp": stamp, "metrics": m}))
    return m


def _compute_metrics(clip_id):
    tl = _tl(clip_id)
    mins = max(tl["duration_s"] / 60, 1e-6)
    t_state = {}
    work_runs = []
    for s in tl["states"]:
        d = s["t_end"] - s["t_start"]
        t_state[s["state"]] = t_state.get(s["state"], 0) + d
        if s["state"] == "work":
            work_runs.append(d)
    ev = {}
    for e in tl["events"]:
        ev.setdefault(e["type"], []).append(e)
    collab = sum(e["t_end"] - e["t_start"] for e in tl["events"]
                 if e["type"] in ("collaboration", "possible_collaboration"))
    return {
        "hands_on_pct": round(100 * t_state.get("work", 0) / tl["duration_s"], 1),
        "search_s_per_min": round(sum(e["t_end"] - e["t_start"] for e in ev.get("search", [])) / mins, 2),
        "idle_s_per_min": round(sum(e["t_end"] - e["t_start"] for e in ev.get("idle", [])) / mins, 2),
        "hesitations_per_min": round(len(ev.get("hesitation", [])) / mins, 2),
        "path_efficiency": path_efficiency(clip_id),
        # how often work is broken off (non-work spells between work spells)
        "interruptions_per_min": round(max(0, len(work_runs) - 1) / mins, 2),
        "collaboration_s_per_min": round(collab / mins, 2),  # context only, never scored
    }


def _all_clips():
    return sorted(p.parent.name for p in OUT.glob("*/timeline.json") if not p.parent.name.startswith("zz-"))


def baseline(clip_id, cache=None):
    """Leave-one-out baseline from the same station (falls back to all stations if too few)."""
    cache = cache if cache is not None else {}
    st = station_of(clip_id)
    peers = [c for c in _all_clips() if station_of(c) == st and c != clip_id]
    scope = "station"
    if not peers:  # a station seen only once: no fair baseline, compare with everything and say so
        peers = [c for c in _all_clips() if c != clip_id]
        scope = "all stations"
    reliability = "high" if len(peers) >= 5 and scope == "station" else         "medium" if len(peers) >= 3 and scope == "station" else "low"
    rows = [cache.setdefault(c, metrics(c)) for c in peers]
    base = {}
    for name, *_ in METRICS:
        vals = [r[name] for r in rows if r.get(name) is not None]
        if not vals:
            continue
        med = statistics.median(vals)
        mad = statistics.median([abs(v - med) for v in vals])
        floor = max(SCALE_FLOOR[name], REL_FLOOR * abs(med))
        base[name] = {"median": round(med, 2), "scale": round(max(1.4826 * mad, floor), 2)}
    return {"station": st, "scope": scope, "recordings": peers, "reliability": reliability, "metrics": base}


def level(score):
    if score >= C.PROFICIENCY_ADVANCED:
        return "Advanced"
    if score >= C.PROFICIENCY_NEEDS_TRAINING:
        return "Intermediate"
    return "Needs training"


# which timeline events explain a below-baseline metric (cited as evidence)
EVIDENCE_TYPE = {"search_s_per_min": ("search",), "idle_s_per_min": ("idle",), "hesitations_per_min": ("hesitation",),
                 "hands_on_pct": ("idle", "search", "transit"), "interruptions_per_min": ("idle", "search", "transit")}


def score(clip_id, cache=None):
    cache = cache if cache is not None else {}
    m = cache.setdefault(clip_id, metrics(clip_id))
    base = baseline(clip_id, cache)
    tl = _tl(clip_id)
    rows, subs = [], []
    for name, unit, higher, label in METRICS:
        b = base["metrics"].get(name)
        v = m.get(name)
        if b is None or v is None:
            continue
        z = (v - b["median"]) / b["scale"] * (1 if higher else -1)
        sub = float(np.clip(50 + 20 * z, 0, 100))
        subs.append(sub)
        better = z > 0.25
        worse = z < -0.25
        ratio = v / b["median"] if b["median"] else None
        text = (f"{label}: {v}{unit} vs baseline {b['median']}{unit}"
                + (f" ({ratio:.1f}x)" if ratio and abs(ratio - 1) > 0.05 else "")
                + (", better than baseline" if better else ", below baseline" if worse else ", in line with baseline"))
        evidence = []
        if worse and name in EVIDENCE_TYPE:
            evs = sorted((e for e in tl["events"] if e["type"] in EVIDENCE_TYPE[name]),
                         key=lambda e: e["t_start"] - e["t_end"])[:3]
            evidence = [f"[{clip_id}@{fmt_t(e['t_start'])}]" for e in evs]
        rows.append({"metric": name, "label": label, "unit": unit, "value": v, "baseline": b["median"],
                     "z": round(z, 2), "subscore": round(sub), "direction": "better" if better else
                     "worse" if worse else "same", "explanation": text, "evidence": evidence})
    total = round(statistics.mean(subs)) if subs else None
    return {
        "clip_id": clip_id, "station": base["station"], "baseline_scope": base["scope"],
        "baseline_recordings": len(base["recordings"]), "baseline_reliability": base["reliability"],
        "score": total, "level": level(total) if total is not None else None,
        "level_note": "Describes how this recording's workflow compares with the station baseline, not a person.",
        "metrics": rows, "fingerprint": {r["label"]: r["subscore"] for r in rows},
        "context": {"collaboration_s_per_min": m["collaboration_s_per_min"]},
        "thresholds": {"advanced": C.PROFICIENCY_ADVANCED, "needs_training": C.PROFICIENCY_NEEDS_TRAINING},
        "method": "Sub-score = 50 + 20 x robust z-score vs the station's leave-one-out median (MAD scale); "
                  "score = mean of sub-scores.",
    }


def station_curve(station, cache=None):
    """Score of every recording of a station, in recording order (a learning curve if they are sequential)."""
    cache = cache if cache is not None else {}
    return [{"clip_id": c, "score": score(c, cache)["score"]} for c in _all_clips() if station_of(c) == station]


if __name__ == "__main__":
    r = score(sys.argv[1])
    print(f"{r['clip_id']}: {r['score']} ({r['level']}) vs {r['baseline_recordings']} recordings "
          f"({r['baseline_scope']}, reliability {r['baseline_reliability']})")
    for row in r["metrics"]:
        print(" -", row["explanation"], " ".join(row["evidence"]))
