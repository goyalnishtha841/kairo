"""Run the full pipeline for one or more clips: perception -> temporal verification -> timeline -> web proxy -> shift report.

Usage:
    python pipeline.py MTL-SGF00106-021 MTL-SGF00106-023        # by clip id
    python pipeline.py --all                                     # every clip in data/raw
    python pipeline.py --all --skip-existing
    python pipeline.py --all --rebuild                           # re-derive timelines from stored tracks
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
import collaboration  # noqa: E402
import config as C  # noqa: E402
import social  # noqa: E402
import timeline  # noqa: E402
import verify  # noqa: E402
import web_proxy  # noqa: E402

RAW = ROOT / "data" / "raw"
OUT = ROOT / "outputs"
ENGINE = copilot.available_engine()


def station_of(clip_id):
    return clip_id.rsplit("-", 1)[0]


def process(clip_id, stride=2, skip_existing=False):
    video = RAW / f"{clip_id}.mp4"
    out = OUT / clip_id
    if not (skip_existing and (out / "hands.json").exists()):
        print(f"[{clip_id}] hand tracking + head motion ...")
        hands.run(video, stride=stride)
        print(f"[{clip_id}] temporal verification (bridge flicker, reject blips) ...")
        verify.apply(clip_id, fresh=True)
    print(f"[{clip_id}] timeline ...")
    timeline.build(clip_id, keyframes=True)
    if not (out / "social.json").exists():
        print(f"[{clip_id}] people, faces and voice activity ...")
        social.run(video)
    collaboration.apply(clip_id)
    tool_classes = C.STATION_TOOLS.get(station_of(clip_id))
    if tool_classes and not (out / "tools.json").exists():
        print(f"[{clip_id}] tool detection ({len(tool_classes)} classes, unvalidated) ...")
        try:
            import tools as tool_detect  # lazy: pulls in ultralytics + CLIP only when actually configured
            import apply_tools
            tool_detect.run(video, tool_classes)
            n = apply_tools.apply(clip_id)
            if n:
                print(f"[{clip_id}] tool masks (SAM 2 tiny, unvalidated) ...")
                import tool_mask
                tool_mask.generate(clip_id)
        except Exception as e:  # optional dependency / model download failure never blocks the pipeline
            print(f"[{clip_id}] tool detection skipped: {type(e).__name__}: {e}")
    if ENGINE != "rules":
        print(f"[{clip_id}] captioning SOP steps ({ENGINE}) ...")
        try:
            sop_labels.caption_clip(clip_id, ENGINE, force=True)
        except Exception as e:  # keep motion-based names if the API is unavailable
            print(f"[{clip_id}] captioning skipped: {type(e).__name__}: {e}")
    print(f"[{clip_id}] web proxy ...")
    web_proxy.make_proxy(video)


def rebuild(clip_id):
    """Re-derive a processed clip from its stored tracks (no video re-tracking, no captioning API):
    temporal verification -> timeline -> collaboration, keeping existing step captions where steps match."""
    old = json.loads((OUT / clip_id / "timeline.json").read_text())["steps"]
    verify.apply(clip_id)
    tl = timeline.build(clip_id, keyframes=True)
    kept = sop_labels.carry_over(old, tl["steps"])
    (OUT / clip_id / "timeline.json").write_text(json.dumps(tl, indent=1))
    collaboration.apply(clip_id)
    print(f"[{clip_id}] rebuilt: {len(tl['steps'])} steps, {kept} captions kept")
    return kept, len(tl["steps"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--stride", type=int, default=2)
    ap.add_argument("--rebuild", action="store_true", help="re-derive timelines of processed clips from stored tracks")
    ap.add_argument("--no-captions", action="store_true", help="skip LLM step names (run ai/recaption.py later)")
    a = ap.parse_args()
    if a.no_captions:
        ENGINE = "rules"
    clips = sorted(p.stem for p in RAW.glob("*.mp4")) if a.all else a.clips
    for c in clips:
        if a.rebuild:
            rebuild(c)
        else:
            process(c, a.stride, a.skip_existing)
    done = sorted(p.parent.name for p in OUT.glob("*/timeline.json"))
    report = insights.analyse(done)
    (OUT / "shift_report.json").write_text(json.dumps(report, indent=1))
    print(report["headline"])
