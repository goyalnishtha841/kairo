"""Run the full pipeline for one or more clips: perception -> timeline -> web proxy -> shift report.

Usage:
    python pipeline.py MTL-SGF00106-021 MTL-SGF00106-023        # by clip id
    python pipeline.py --all                                     # every clip in data/raw
    python pipeline.py --all --skip-existing
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for sub in ("perception", "events", "ai"):
    sys.path.insert(0, str(ROOT / sub))

import copilot  # noqa: E402
import hands  # noqa: E402
import sop_labels  # noqa: E402
import insights  # noqa: E402
import timeline  # noqa: E402
import web_proxy  # noqa: E402

RAW = ROOT / "data" / "raw"
OUT = ROOT / "outputs"
ENGINE = copilot.available_engine()


def process(clip_id, stride=2, skip_existing=False):
    video = RAW / f"{clip_id}.mp4"
    out = OUT / clip_id
    if not (skip_existing and (out / "hands.json").exists()):
        print(f"[{clip_id}] hand tracking + head motion ...")
        hands.run(video, stride=stride)
    print(f"[{clip_id}] timeline ...")
    timeline.build(clip_id, keyframes=True)
    if ENGINE != "rules":
        print(f"[{clip_id}] captioning SOP steps ({ENGINE}) ...")
        try:
            sop_labels.caption_clip(clip_id, ENGINE, force=True)
        except Exception as e:  # keep motion-based names if the API is unavailable
            print(f"[{clip_id}] captioning skipped: {type(e).__name__}: {e}")
    print(f"[{clip_id}] web proxy ...")
    web_proxy.make_proxy(video)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--stride", type=int, default=2)
    a = ap.parse_args()
    clips = sorted(p.stem for p in RAW.glob("*.mp4")) if a.all else a.clips
    for c in clips:
        process(c, a.stride, a.skip_existing)
    done = sorted(p.parent.name for p in OUT.glob("*/timeline.json"))
    report = insights.analyse(done)
    (OUT / "shift_report.json").write_text(json.dumps(report, indent=1))
    print(report["headline"])
