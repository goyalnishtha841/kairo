"""SOP Compliance Checker (USP 7): compare a clip's detected steps against a declared SOP template.

Reuses the step-label similarity matching from compare.py (bag-of-words token overlap) so it tolerates
caption wording differences, but aligns against a fixed list of expected step names instead of another
clip's steps. Flags missing steps, out-of-order steps, extra steps not in the SOP, and skipped
mandatory steps (e.g. an inspection that must never be skipped).

Usage: python events/sop.py <clip_id> "Open panel" "Disconnect power" "Remove screw" "Inspect" "Close panel"
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from insights import fmt_t  # noqa: E402

STOP = {"a", "an", "the", "with", "of", "to", "into", "and", "on", "in", "piece", "hand", "hands"}
MATCH_MIN = 0.3


def tokens(label):
    return {w for w in re.findall(r"[a-z]+", (label or "").lower()) if w not in STOP}


def similarity(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def load(clip_id):
    return json.loads((OUT / clip_id / "timeline.json").read_text())


def check(clip_id, expected_steps, mandatory=None):
    """expected_steps: ordered list of step-name strings from the written SOP.
    mandatory: subset of expected_steps that must never be skipped (e.g. an inspection step)."""
    tl = load(clip_id)
    steps = tl["steps"]
    mandatory = set(mandatory or [])

    used, rows, cursor = set(), [], 0
    for exp in expected_steps:
        best_i, best_s = None, 0.0
        for i, st in enumerate(steps):
            if i in used:
                continue
            s = similarity(exp, st["label"])
            if s > best_s:
                best_i, best_s = i, s
        if best_i is not None and best_s >= MATCH_MIN:
            used.add(best_i)
            st = steps[best_i]
            out_of_order = best_i < cursor
            cursor = max(cursor, best_i + 1)
            rows.append({"expected": exp, "status": "out_of_order" if out_of_order else "done",
                         "matched_step": st["step_id"], "matched_label": st["label"],
                         "similarity": round(best_s, 2), "t_start": st["t_start"],
                         "cite": f"[{clip_id}@{fmt_t(st['t_start'])}]"})
        else:
            rows.append({"expected": exp, "status": "missing", "matched_step": None, "matched_label": None,
                         "similarity": 0.0, "t_start": None, "cite": None})

    extra = [{"step_id": st["step_id"], "label": st["label"], "t_start": st["t_start"],
              "cite": f"[{clip_id}@{fmt_t(st['t_start'])}]"} for i, st in enumerate(steps) if i not in used]

    missing = [r for r in rows if r["status"] == "missing"]
    out_of_order = [r for r in rows if r["status"] == "out_of_order"]
    skipped_mandatory = [r["expected"] for r in missing if r["expected"] in mandatory]
    compliant = not missing and not out_of_order

    findings = []
    for r in missing:
        tag = " (mandatory)" if r["expected"] in mandatory else ""
        findings.append(f"Missing step: \"{r['expected']}\"{tag} was never observed.")
    for r in out_of_order:
        findings.append(f"Out of order: \"{r['expected']}\" happened at step {r['matched_step']} {r['cite']}.")
    for e in extra:
        findings.append(f"Extra step not in the SOP: \"{e['label']}\" {e['cite']}.")

    return {
        "clip_id": clip_id, "expected_steps": expected_steps, "rows": rows, "extra_steps": extra,
        "compliant": compliant, "missing_count": len(missing), "out_of_order_count": len(out_of_order),
        "skipped_mandatory": skipped_mandatory,
        "adherence_pct": round(100 * (len(expected_steps) - len(missing)) / max(len(expected_steps), 1)),
        "findings": findings,
        "headline": ("SOP followed in full." if compliant else
                     f"{len(missing)} missing, {len(out_of_order)} out of order"
                     + (f", including a skipped mandatory step: {', '.join(skipped_mandatory)}"
                        if skipped_mandatory else "") + "."),
    }


if __name__ == "__main__":
    r = check(sys.argv[1], sys.argv[2:])
    print(json.dumps(r, indent=1))
