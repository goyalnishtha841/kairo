"""SOP comparator: align a target clip's steps against a reference clip's steps.

Steps are matched by name/tool similarity with a Needleman-Wunsch alignment (order-preserving),
then unmatched steps that have a good partner elsewhere are reported as out of order.

Usage: python events/compare.py <reference_clip> <target_clip>
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(ROOT / "events"))
from insights import fmt_t  # noqa: E402

STOP = {"a", "an", "the", "with", "of", "to", "into", "and", "on", "in", "piece", "hand", "hands"}
GAP = -0.35          # cost of a missing/extra step
MATCH_MIN = 0.34     # similarity above which two steps are "the same step"
SLOW_PCT = 40        # duration difference that counts as notably slower/faster
FRICTION = ("search", "transit", "idle", "hesitation", "extra_reach", "reattempt")


def load(clip_id):
    return json.loads((OUT / clip_id / "timeline.json").read_text())


def tokens(step):
    words = re.findall(r"[a-z]+", (step.get("label") or "").lower())
    toks = {w.rstrip("s") for w in words if w not in STOP and len(w) > 2}
    if step.get("tool"):
        toks |= {"tool:" + w for w in re.findall(r"[a-z]+", step["tool"].lower()) if len(w) > 2}
    return toks


def similarity(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def align(ref, tgt):
    n, m = len(ref), len(tgt)
    S = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        S[i][0] = i * GAP
    for j in range(1, m + 1):
        S[0][j] = j * GAP
    sim = [[similarity(r, t) for t in tgt] for r in ref]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            S[i][j] = max(S[i - 1][j - 1] + sim[i - 1][j - 1] - MATCH_MIN,
                          S[i - 1][j] + GAP, S[i][j - 1] + GAP)
    pairs, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and S[i][j] == S[i - 1][j - 1] + sim[i - 1][j - 1] - MATCH_MIN:
            pairs.append((i - 1, j - 1, sim[i - 1][j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and S[i][j] == S[i - 1][j] + GAP:
            pairs.append((i - 1, None, 0.0))
            i -= 1
        else:
            pairs.append((None, j - 1, 0.0))
            j -= 1
    return pairs[::-1], sim


def friction_per_min(tl):
    mins = max(tl["duration_s"] / 60, 1e-6)
    out = {k: 0.0 for k in FRICTION}
    for e in tl["events"]:
        if e["type"] in out:
            out[e["type"]] += e["t_end"] - e["t_start"]
    return {k: round(v / mins, 1) for k, v in out.items()}


def compare(ref_id, tgt_id):
    ref_tl, tgt_tl = load(ref_id), load(tgt_id)
    ref, tgt = ref_tl["steps"], tgt_tl["steps"]
    pairs, sim = align(ref, tgt)

    rows = []
    for ri, ti, s in pairs:
        r = ref[ri] if ri is not None else None
        t = tgt[ti] if ti is not None else None
        if r and t and s >= MATCH_MIN:
            d = t["duration_s"] - r["duration_s"]
            pct = 100 * d / max(r["duration_s"], 1e-6)
            status = "slower" if pct > SLOW_PCT else "faster" if pct < -SLOW_PCT else "match"
            rows.append({"status": status, "ref": r, "target": t, "similarity": round(s, 2),
                         "delta_s": round(d, 1), "delta_pct": round(pct)})
        else:  # alignment paired two dissimilar steps -> one missing + one extra
            if r:
                rows.append({"status": "missing", "ref": r, "target": None, "similarity": 0})
            if t:
                rows.append({"status": "extra", "ref": None, "target": t, "similarity": 0})

    # a "missing" ref step whose best partner is an "extra" target step = done out of order
    extras = {id(x["target"]): x for x in rows if x["status"] == "extra"}
    for row in rows:
        if row["status"] != "missing":
            continue
        ri = ref.index(row["ref"])
        best = max(((sim[ri][tgt.index(x["target"])], x) for x in extras.values()), default=(0, None),
                   key=lambda p: p[0])
        if best[1] is not None and best[0] >= MATCH_MIN:
            row.update(status="out_of_order", target=best[1]["target"], similarity=round(best[0], 2))
            best[1]["status"] = "_merged"
            extras.pop(id(best[1]["target"]))
    rows = [x for x in rows if x["status"] != "_merged"]

    ref_work = sum(s["duration_s"] for s in ref)
    tgt_work = sum(s["duration_s"] for s in tgt)
    fr_ref, fr_tgt = friction_per_min(ref_tl), friction_per_min(tgt_tl)

    def c(t):
        return f"[{tgt_id}@{fmt_t(t)}]"

    findings = []
    for x in rows:
        if x["status"] == "missing":
            findings.append(f"Missing step: \"{x['ref']['label']}\" (reference step {x['ref']['step_id']}) was not observed.")
        elif x["status"] == "out_of_order":
            findings.append(f"Out of order: \"{x['ref']['label']}\" done at a different point {c(x['target']['t_start'])}.")
        elif x["status"] == "extra":
            findings.append(f"Extra step: \"{x['target']['label']}\" is not in the reference {c(x['target']['t_start'])}.")
        elif x["status"] == "slower":
            findings.append(f"Slower: \"{x['ref']['label']}\" took {x['target']['duration_s']:.0f}s vs "
                            f"{x['ref']['duration_s']:.0f}s (+{x['delta_pct']}%) {c(x['target']['t_start'])}.")
    for k, label in (("search", "searching"), ("idle", "idle time"), ("hesitation", "hesitation"),
                     ("reattempt", "repeated corrections")):
        if fr_tgt[k] - fr_ref[k] >= 2:
            findings.append(f"More {label}: {fr_tgt[k]}s/min vs {fr_ref[k]}s/min in the reference.")

    counts = {k: sum(1 for x in rows if x["status"] == k)
              for k in ("match", "slower", "faster", "missing", "extra", "out_of_order")}
    matched = counts["match"] + counts["slower"] + counts["faster"]
    return {
        "reference": ref_id, "target": tgt_id,
        "rows": rows, "counts": counts,
        "adherence_pct": round(100 * matched / max(len(ref), 1)),
        "hands_on_s": {"reference": round(ref_work, 1), "target": round(tgt_work, 1),
                       "delta": round(tgt_work - ref_work, 1)},
        "friction_s_per_min": {"reference": fr_ref, "target": fr_tgt},
        "findings": findings,
    }


if __name__ == "__main__":
    r = compare(sys.argv[1], sys.argv[2])
    print(f"adherence {r['adherence_pct']}%  counts {r['counts']}  hands-on {r['hands_on_s']}")
    for f in r["findings"]:
        print(" -", f)
