"""Motion Skill Profiler: expert-like vs beginner-like motion patterns, learned without labels.

The Proficiency Engine compares how time is spent. This module looks at HOW the hands move. For each
recording it measures motor-control features from the wearer's own hand tracks (head motion removed,
so looking around does not count as hand motion), normalises them against the same station, and
clusters all recordings without labels. The cluster whose centre is smoother, more direct and calmer
is named the expert-like pattern. It describes motion in a recording, never a person.

Features (all per recording):
    smoothness          SPARC spectral arc length of each movement's speed profile (closer to 0 = smoother)
    peak_speed          median peak hand speed per movement (frame-widths/s)
    corrections         extra speed peaks per movement (sub-movements = online corrections)
    regrasps_per_min    grip closes again at the same spot shortly after a release
    motion_entropy      entropy of movement directions, 0-1 (1 = erratic, every direction equally likely)
    idle_s_per_min      idle time from the timeline
    head_scan_s_per_min time spent scanning the scene with the head (looking around)

Usage: python events/skill_profile.py [MTL-SGF00106-023]
"""
import json
import statistics
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from insights import fmt_t  # noqa: E402
from proficiency import _all_clips, station_of  # noqa: E402
from timeline import HEAD_SCAN, V_MOVE  # noqa: E402

# name, unit, expert_direction (+1 = higher is more expert-like), label, decimals
FEATURES = [
    ("smoothness", "", +1, "Trajectory smoothness", 2),
    ("peak_speed", "fw/s", +1, "Hand speed", 2),
    ("corrections", "/move", -1, "Corrections", 2),
    ("regrasps_per_min", "/min", -1, "Repeated grasps", 2),
    ("motion_entropy", "", -1, "Motion entropy", 2),
    ("idle_s_per_min", "s/min", -1, "Idle time", 1),
    ("head_scan_s_per_min", "s/min", -1, "Looking around", 1),
]
# smallest difference that matters: max(absolute floor, 20% of the station median)
SCALE_FLOOR = {"smoothness": 0.05, "peak_speed": 0.03, "corrections": 0.15, "regrasps_per_min": 0.5,
               "motion_entropy": 0.03, "idle_s_per_min": 2.0, "head_scan_s_per_min": 2.0}
REL_FLOOR = 0.20

ASPECT = 9 / 16           # processed frames are 16:9; y is normalised by height, convert to frame widths
MOVE_END = 0.5 * V_MOVE   # a movement ends when speed falls below this
MIN_MOVE_S, MAX_MOVE_S = 0.3, 4.0
GRIP_CLOSED, GRIP_OPEN = 0.30, 0.55   # thumb-index gap / palm length (hysteresis)
REGRASP_S, REGRASP_DIST = 2.0, 0.06   # a close within 2 s and 6% of frame width of the last release
MIN_MOVES = 30            # fewer hand movements than this: too little motion to profile reliably
SPARC_FC = 6.0            # Hz; tracks are ~15 Hz so this stays under Nyquist
PATTERNS = {2: ["Expert-like", "Beginner-like"], 3: ["Expert-like", "Developing", "Beginner-like"]}
NOTE = "Describes the motion in this recording compared with its station, not a person. No identity is used."


# ---------------------------------------------------------------- kinematics
def sparc(speed, fs, fc=SPARC_FC, amp_th=0.05, pad=4):
    """Spectral arc length of a speed profile (Balasubramanian et al. 2015). 0 is perfectly smooth."""
    n = int(2 ** np.ceil(np.log2(len(speed)) + pad))
    f = np.arange(n) * fs / n
    mag = np.abs(np.fft.fft(speed, n))
    mag = mag / (mag.max() or 1.0)
    sel = f <= fc
    f, mag = f[sel], mag[sel]
    above = np.nonzero(mag >= amp_th)[0]
    f, mag = f[:above[-1] + 1], mag[:above[-1] + 1]
    df = np.diff(f) / (f[-1] - f[0] or 1.0)
    return -float(np.sum(np.sqrt(df ** 2 + np.diff(mag) ** 2)))


def _tracks(hands):
    """Per hand: time, palm centre in frame widths, scene-compensated velocity, grip aperture (NaN when unseen)."""
    fr = hands["frames"]
    t = np.array([f["t"] for f in fr])
    cam = np.array([[f["cam"]["pan"], f["cam"]["tilt"]] if f.get("cam", {}).get("ok") else [0.0, 0.0]
                    for f in fr])
    out = {}
    for hid in ("L", "R"):
        pos = np.full((len(fr), 2), np.nan)
        grip = np.full(len(fr), np.nan)
        for i, f in enumerate(fr):
            hd = next((h for h in f["hands"] if h["id"] == hid and not h.get("bridged")), None)
            if hd is None:
                continue
            lm = np.array(hd["lm"])[:, :2] * [1.0, ASPECT]
            pos[i] = lm[[0, 5, 9, 13, 17]].mean(0)
            grip[i] = np.linalg.norm(lm[4] - lm[8]) / max(np.linalg.norm(lm[0] - lm[9]), 1e-6)
        dt = np.gradient(t)
        # hand motion relative to the scene = image motion minus the scene's own image motion (head)
        vel = np.gradient(pos, axis=0) / dt[:, None] - cam
        out[hid] = {"t": t, "pos": pos, "vel": vel, "grip": grip}
    return out


def _movements(tr):
    """Contiguous visible runs where speed rises above V_MOVE, extended until it drops below MOVE_END."""
    speed = np.linalg.norm(tr["vel"], axis=1)
    t, moves, i, n = tr["t"], [], 0, len(speed)
    while i < n:
        if not (speed[i] > V_MOVE):
            i += 1
            continue
        a = i
        while a > 0 and speed[a - 1] > MOVE_END:
            a -= 1
        b = i
        while b + 1 < n and speed[b + 1] > MOVE_END:
            b += 1
        if MIN_MOVE_S <= t[b] - t[a] <= MAX_MOVE_S:
            moves.append((a, b))
        i = b + 1
    return moves, speed


def _peaks(s):
    """Local speed maxima that rise clearly above the valley before them (ignores tracking ripple)."""
    peaks, valley = [], s[0]
    for i in range(1, len(s) - 1):
        valley = min(valley, s[i])
        if s[i] >= s[i - 1] and s[i] > s[i + 1] and s[i] - valley > 0.25 * V_MOVE:
            peaks.append(i)
            valley = s[i]
    return peaks or [int(np.argmax(s))]


def _regrasps(tr):
    """Grip closes again near where it was last released, soon after: a repeated grasp."""
    events, closed, last_release = [], False, None
    for i, g in enumerate(tr["grip"]):
        if np.isnan(g):
            continue
        if not closed and g < GRIP_CLOSED:
            closed = True
            if last_release is not None:
                t0, p0 = last_release
                if tr["t"][i] - t0 <= REGRASP_S and np.linalg.norm(tr["pos"][i] - p0) <= REGRASP_DIST:
                    events.append(float(tr["t"][i]))
        elif closed and g > GRIP_OPEN:
            closed = False
            last_release = (tr["t"][i], tr["pos"][i])
    return events


def features(clip_id):
    """Motion features of one recording, cached on disk until its hand tracks or timeline change."""
    d = OUT / clip_id
    stamp = [round((d / f).stat().st_mtime, 3) for f in ("timeline.json", "hands.json") if (d / f).exists()]
    cache_file = d / "skill_features.json"
    if cache_file.exists():
        cached = json.loads(cache_file.read_text())
        if cached.get("stamp") == stamp:
            return cached["features"]
    f = _compute_features(clip_id)
    cache_file.write_text(json.dumps({"stamp": stamp, "features": f}))
    return f


def _compute_features(clip_id):
    hands = json.loads((OUT / clip_id / "hands.json").read_text())
    tl = json.loads((OUT / clip_id / "timeline.json").read_text())
    mins = max(tl["duration_s"] / 60, 1e-6)
    tracks = _tracks(hands)
    fs = 1.0 / float(np.median(np.diff(tracks["L"]["t"])))
    sm, pk, corr, dirs, wts, jerky, regrasp_t = [], [], [], [], [], [], []
    for hid, tr in tracks.items():
        moves, speed = _movements(tr)
        for a, b in moves:
            s = speed[a:b + 1]
            sp = sparc(s, fs)
            n_peaks = len(_peaks(s))
            sm.append(sp)
            pk.append(float(s.max()))
            corr.append(n_peaks - 1)
            v = tr["vel"][a:b + 1]
            dirs.extend(np.arctan2(v[:, 1], v[:, 0]))
            wts.extend(s)
            jerky.append((sp, n_peaks - 1, float(tr["t"][a]), hid))
        regrasp_t.extend(_regrasps(tr))
    if dirs:
        hist, _ = np.histogram(dirs, bins=8, range=(-np.pi, np.pi), weights=wts)
        p = hist / hist.sum()
        entropy = float(-np.sum(p[p > 0] * np.log(p[p > 0])) / np.log(8))
    else:
        entropy = None
    head = np.array([abs(f["cam"]["pan"]) + abs(f["cam"]["tilt"]) if f.get("cam", {}).get("ok") else 0.0
                     for f in hands["frames"]])
    dt = float(np.median(np.diff(tracks["L"]["t"])))
    idle = sum(e["t_end"] - e["t_start"] for e in tl["events"] if e["type"] == "idle")
    # the moments that best show each feature (for evidence links)
    worst = sorted(jerky, key=lambda m: (-m[1], m[0]))[:3]
    return {
        "smoothness": round(statistics.median(sm), 3) if sm else None,
        "peak_speed": round(statistics.median(pk), 3) if pk else None,
        "corrections": round(float(np.mean(corr)), 3) if corr else None,
        "regrasps_per_min": round(len(regrasp_t) / mins, 2),
        "motion_entropy": round(entropy, 3) if entropy is not None else None,
        "idle_s_per_min": round(idle / mins, 2),
        "head_scan_s_per_min": round(float(np.sum(head > HEAD_SCAN)) * dt / mins, 2),
        "movements": len(sm),
        "evidence": {"corrections": [m[2] for m in worst if m[1] > 0],
                     "regrasps_per_min": sorted(regrasp_t)[:3]},
    }


# ---------------------------------------------------------------- normalise and cluster
def _station_z(rows):
    """Signed robust z per station: +1 = one 'meaningful difference' more expert-like than the station median."""
    by_station = {}
    for c in rows:
        by_station.setdefault(station_of(c), []).append(c)
    z, ref = {}, {}
    for st, clips in by_station.items():
        ref[st] = {}
        for name, _, sign, *_ in FEATURES:
            vals = [rows[c][name] for c in clips if rows[c].get(name) is not None]
            if not vals:
                continue
            med = statistics.median(vals)
            mad = statistics.median([abs(v - med) for v in vals])
            scale = max(1.4826 * mad, SCALE_FLOOR[name], REL_FLOOR * abs(med))
            ref[st][name] = {"median": med, "scale": scale}
        for c in clips:
            z[c] = [sign * (rows[c][n] - ref[st][n]["median"]) / ref[st][n]["scale"]
                    if rows[c].get(n) is not None and n in ref[st] else 0.0 for n, _, sign, *_ in FEATURES]
    return z, ref, {st: len(cl) for st, cl in by_station.items()}


def kmeans(X, k, restarts=10, iters=100, seed=0):
    """Plain k-means++ with restarts (deterministic for a seed). Returns labels, centres, inertia."""
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(restarts):
        C = [X[rng.integers(len(X))]]
        for _ in range(1, k):
            d2 = np.min([np.sum((X - c) ** 2, 1) for c in C], 0)
            C.append(X[rng.choice(len(X), p=d2 / d2.sum())] if d2.sum() > 0 else X[rng.integers(len(X))])
        C = np.array(C)
        for _ in range(iters):
            lab = np.argmin(((X[:, None] - C[None]) ** 2).sum(-1), 1)
            new = np.array([X[lab == j].mean(0) if np.any(lab == j) else C[j] for j in range(k)])
            if np.allclose(new, C):
                break
            C = new
        inertia = float(((X - C[lab]) ** 2).sum())
        if best is None or inertia < best[2]:
            best = (lab, C, inertia)
    return best


def silhouette(X, lab):
    D = np.linalg.norm(X[:, None] - X[None], axis=-1)
    s = []
    for i in range(len(X)):
        same = (lab == lab[i])
        if same.sum() <= 1:
            s.append(0.0)
            continue
        a = D[i, same].sum() / (same.sum() - 1)
        b = min(D[i, lab == j].mean() for j in set(lab) if j != lab[i])
        s.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)
    return float(np.mean(s))


def profile_all(cache=None):
    """Features, station-normalised z-vectors and an unsupervised clustering of every recording."""
    if cache is not None and "_skill" in cache:
        return cache["_skill"]
    clips = _all_clips()
    rows = {c: features(c) for c in clips}
    z, ref, sizes = _station_z(rows)
    Z = np.array([z[c] for c in clips])
    # fit only on stations with a usable baseline (>= 3 recordings); the rest join the nearest cluster
    fit_idx = [i for i, c in enumerate(clips) if sizes[station_of(c)] >= 3]
    if len(fit_idx) < 6:
        fit_idx = list(range(len(clips)))
    # equal weight per feature, so one high-variance feature (e.g. idle time) cannot decide alone
    sd = Z[fit_idx].std(0)
    X = Z / np.where(sd > 1e-9, sd, 1.0)
    # Cluster along the expertise axis (mean of the signed features). In the full 7-D space the
    # recordings group by working style rather than by skill, so a label there would contradict its
    # own evidence. Each feature's sign is a motor-learning prior (smoother, fewer corrections,
    # less idle = more practised), not a label.
    E = X.mean(1, keepdims=True)
    Ef = E[fit_idx]
    # choose k by silhouette; k=3 only when there is enough data to support three groups
    options = [2] + ([3] if len(fit_idx) >= 12 else [])
    fits = {k: kmeans(Ef, k) for k in options if len(fit_idx) > k}
    k = max(fits, key=lambda k: silhouette(Ef, fits[k][0]))
    _, C, _ = fits[k]
    lab = np.argmin(np.abs(E - C.T), 1)
    order = np.argsort(-C[:, 0])   # highest centre = expert-like
    name = {int(j): PATTERNS[k][r] for r, j in enumerate(order)}
    res = {"clips": clips, "rows": rows, "z": z, "ref": ref, "station_sizes": sizes, "X": X, "Z": Z, "E": E[:, 0],
           "labels": lab, "centres": C, "k": k, "names": name, "fit_on": len(fit_idx),
           "silhouette": round(silhouette(Ef, fits[k][0]), 2)}
    if cache is not None:
        cache["_skill"] = res
    return res


# ---------------------------------------------------------------- explain one recording
def profile(clip_id, cache=None):
    P = profile_all(cache)
    if clip_id not in P["clips"]:
        raise KeyError(clip_id)
    i = P["clips"].index(clip_id)
    x, C, lab = P["X"][i], P["centres"], P["labels"]
    d = np.abs(C[:, 0] - P["E"][i])
    own = int(lab[i])
    other = np.min(np.delete(d, own)) if len(d) > 1 else d[own]
    confidence = round(float(other / (d[own] + other)) if d[own] + other > 0 else 0.5, 2)
    st = station_of(clip_id)
    row, ref = P["rows"][clip_id], P["ref"][st]
    feats = []
    for j, (n, unit, sign, label, dec) in enumerate(FEATURES):
        if row.get(n) is None or n not in ref:
            continue
        zj = float(x[j])   # equal-weight scale, the same one the index and clusters use
        tone = "expert" if zj > 0.5 else "beginner" if zj < -0.5 else "typical"
        ev = [f"[{clip_id}@{fmt_t(t)}]" for t in row["evidence"].get(n, [])] if tone == "beginner" else []
        feats.append({"feature": n, "label": label, "unit": unit, "value": round(row[n], dec),
                      "station_median": round(ref[n]["median"], dec), "z": round(zj, 2), "tone": tone,
                      "evidence": ev})
    strong = sorted((f for f in feats if f["tone"] == "expert"), key=lambda f: -f["z"])[:2]
    weak = sorted((f for f in feats if f["tone"] == "beginner"), key=lambda f: f["z"])[:2]
    pattern = P["names"][own]

    def phrase(f):
        return f"{f['label'].lower()} {f['value']}{f['unit']} vs {f['station_median']}{f['unit']}"

    # lead with the features that agree with the pattern, then the ones that pull the other way
    lead, other = (weak, strong) if pattern == "Beginner-like" else (strong, weak)
    summary = f"This recording shows {pattern.lower()} motion patterns"
    if lead:
        summary += ": " + ", ".join(phrase(f) for f in lead)
    elif not other:
        summary += ", close to the station's typical motion on every feature"
    if other:
        summary += ("; though " if lead else ", the sum of small differences; stands out on ") + \
            ", ".join(phrase(f) for f in other)
    summary += "."
    peers = sorted((float(np.linalg.norm(P["X"][j] - x)), c) for j, c in enumerate(P["clips"]) if c != clip_id)[:3]
    return {
        "clip_id": clip_id, "station": st, "station_recordings": P["station_sizes"][st],
        "pattern": pattern, "confidence": confidence,
        "expertise_index": round(float(np.clip(50 + 20 * P["E"][i], 0, 100))),
        "summary": summary, "features": feats, "movements": row["movements"],
        "fingerprint": {f["label"]: round(float(np.clip(50 + 20 * f["z"], 0, 100))) for f in feats},
        "similar": [{"clip_id": c, "pattern": P["names"][int(lab[P["clips"].index(c)])],
                     "distance": round(dist, 2)} for dist, c in peers],
        "clusters": cluster_map(cache),
        "in_fit": P["station_sizes"][st] >= 3 or P["fit_on"] == len(P["clips"]),
        "reliability": "low" if P["station_sizes"][st] < 3 or row["movements"] < MIN_MOVES else
                       "medium" if P["station_sizes"][st] < 5 else "high",
        "note": NOTE,
        "method": (f"No labels. {len(FEATURES)} motion features per recording, robust z-scores within the station, "
                   f"each feature scaled to equal weight and signed by a motor-learning prior (smoother, fewer "
                   f"corrections, less idle = more practised), then k-means along that axis on {P['fit_on']} "
                   f"recordings (k={P['k']}, silhouette {P['silhouette']}). Index 50 = the station's typical motion."),
    }


def cluster_map(cache=None):
    """Every recording in 2-D for the scatter plot: x = the expertise axis the clusters are cut on,
    y = the main remaining variation (working style, PCA of what the expertise axis leaves)."""
    P = profile_all(cache)
    X = P["X"] - P["X"].mean(0)
    axis = np.ones(X.shape[1]) / np.sqrt(X.shape[1])
    resid = X - np.outer(X @ axis, axis)
    _, _, vt = np.linalg.svd(resid, full_matrices=False)
    ys = resid @ vt[0]
    return [{"clip_id": c, "station": station_of(c), "pattern": P["names"][int(P["labels"][i])],
             "x": round(float(P["E"][i]), 2), "y": round(float(ys[i]), 2)} for i, c in enumerate(P["clips"])]


if __name__ == "__main__":
    cache = {}
    clips = sys.argv[1:] or _all_clips()
    for c in clips:
        r = profile(c, cache)
        print(f"{c}: {r['pattern']} (conf {r['confidence']}, index {r['expertise_index']}) - {r['summary']}")
    print(profile_all(cache)["k"], "clusters, silhouette", profile_all(cache)["silhouette"])
