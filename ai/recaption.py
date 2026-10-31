"""Caption every processed clip whose SOP steps still have motion-based names.

Waits out Groq rate limits (uses the retry time Groq reports) instead of failing, so it can run in
the background until everything is captioned.

Usage: python ai/recaption.py [--max-hours 6]
"""
import glob
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "ai"), str(ROOT / "events")]
import copilot  # noqa: E402
import sop_labels  # noqa: E402

OUT = ROOT / "outputs"


def pending():
    out = []
    for p in sorted(glob.glob(str(OUT / "*" / "timeline.json"))):
        clip = Path(p).parent.name
        if clip.startswith("zz-"):
            continue
        steps = [s for s in json.loads(Path(p).read_text())["steps"] if s.get("keyframe")]
        if steps and not all(s.get("captioned") for s in steps):
            out.append(clip)
    return out


def retry_after(err):
    """Seconds Groq asks us to wait, e.g. 'try again in 9m43.6s'."""
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", str(err))
    if not m:
        return 300
    h, mnt, s = (float(x) if x else 0 for x in m.groups())
    return h * 3600 + mnt * 60 + s + 5


def main(max_hours=6.0):
    engine = copilot.available_engine()
    if engine == "rules":
        print("no LLM key configured", flush=True)
        return
    deadline = time.time() + max_hours * 3600
    while time.time() < deadline:
        todo = pending()
        if not todo:
            print("all clips captioned", flush=True)
            return
        clip = todo[0]
        try:
            n = sop_labels.caption_clip(clip, engine, force=True)
            print(f"{clip}: {n} steps captioned", flush=True)
        except Exception as e:
            wait = retry_after(e) if "429" in str(e) or "rate" in str(e).lower() else 60
            print(f"{clip}: {type(e).__name__}; waiting {wait / 60:.1f} min", flush=True)
            time.sleep(min(wait, max(0, deadline - time.time())))
    print(f"stopped after {max_hours}h; still pending: {pending()}", flush=True)


if __name__ == "__main__":
    hours = float(sys.argv[sys.argv.index("--max-hours") + 1]) if "--max-hours" in sys.argv else 6.0
    main(hours)
