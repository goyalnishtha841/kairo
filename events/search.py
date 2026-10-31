"""Natural Language Factory Search (USP 11): find clips/events/steps matching a free-text query.

No embeddings or trained NLP: a keyword router maps phrases to timeline event types and a step-label
text search, the same evidence-first rule the rest of Kairo follows -- every hit cites a timestamp you
can open. Two of the example queries in the brief have no real detector behind them ("screwdriver was
dropped" needs an object-drop model; "asked for help" needs speech-content understanding, which
docs/STRATEGY.md explicitly rejects for privacy). Rather than fake those, we map them to the closest
real signal and say so in `proxy_notes`.

Usage: python events/search.py "clips where workers struggled with bolt installation"
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from insights import fmt_t, load  # noqa: E402

KEYWORD_TYPE = {
    "search": ("search", "look for", "hunt", "find tool", "missing tool"),
    "transit": ("walk", "fetch", "away from"),
    "idle": ("idle", "wait", "talking", "stopped"),
    "hesitation": ("hesitat", "stall", "struggl", "unsure"),
    "extra_reach": ("reach", "awkward"),
    "reattempt": ("reattempt", "redo", "retry", "drop", "fumbl"),
    "collaboration": ("help", "assist", "together", "collaborat", "ask"),
    "possible_collaboration": ("help", "assist", "ask"),
}
PROXY_NOTE = {
    "drop": "No object-drop detector exists; showing repeated-correction (reattempt) events as the closest proxy.",
    "ask": "No speech-content model exists (by design, for privacy); showing high-confidence collaboration "
           "events as the closest proxy for 'asked for help'.",
}


def _clip_ids():
    return sorted(p.parent.name for p in OUT.glob("*/timeline.json") if not p.parent.name.startswith("zz-"))


def search(query, clip_ids=None):
    clip_ids = clip_ids or _clip_ids()
    ql = query.lower()
    words = set(re.findall(r"[a-z]+", ql))
    kw_words = {w for kws in KEYWORD_TYPE.values() for phrase in kws for w in phrase.split()}
    matched_types = {t for t, kws in KEYWORD_TYPE.items() if any(k in ql for k in kws)}
    proxies = [note for key, note in PROXY_NOTE.items() if key in ql]
    label_words = words - kw_words

    hits = []
    for c in clip_ids:
        tl = load(c)
        for e in tl["events"]:
            if e["type"] in matched_types:
                hits.append({"clip_id": c, "t_start": e["t_start"], "type": e["type"], "note": e["note"],
                             "cite": f"[{c}@{fmt_t(e['t_start'])}]"})
        for s in tl["steps"]:
            lab = (s["label"] or "").lower()
            if label_words and any(w in lab for w in label_words):
                hits.append({"clip_id": c, "t_start": s["t_start"], "type": "step", "note": s["label"],
                             "cite": f"[{c}@{fmt_t(s['t_start'])}]"})
    hits.sort(key=lambda h: (h["clip_id"], h["t_start"]))
    return {"query": query, "matched_types": sorted(matched_types), "hits": hits[:50], "count": len(hits),
            "proxy_notes": proxies}


if __name__ == "__main__":
    import json
    print(json.dumps(search(" ".join(sys.argv[1:])), indent=1))
