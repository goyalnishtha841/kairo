"""Training highlight reel (PS5's own example: "training-video generation"): auto-cut a short,
captioned montage from evidence Kairo already computed -- either the clip's worst friction moments
("what to fix," for a toolbox talk) or its longest friction-free stretches ("how it should look,"
for onboarding). No new judgment calls: moments are selected by the same root-cause/friction ranking
events/root_cause.py and events/insights.py already use, with the exact note text as the caption.

Usage: python events/highlight_reel.py <clip_id> [<clip_id> ...] --mode friction --max-clips 6
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
RAW = ROOT / "data" / "raw"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from insights import fmt_t, load  # noqa: E402
import root_cause  # noqa: E402

PAD_S = 1.0           # seconds of context before/after each moment
MIN_CLIP_S = 2.0      # a moment shorter than this (after padding) is padded up to this
MAX_CLIP_S = 8.0      # a moment longer than this is trimmed to this (keeps the reel tight)
FONT_CANDIDATES = [   # tried in order; drawtext falls back to fontconfig's default if none exist
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _font():
    return next((f for f in FONT_CANDIDATES if Path(f).exists()), None)


CAPTION_MAX_CHARS = 70  # generous at the proxy's 960px width; see _drawtext_escape


def _drawtext_escape(text):
    """Escape a caption for ffmpeg's drawtext filter syntax: backslash, colon, comma and percent
    are all filtergraph-syntax-significant and must be backslash-escaped, not just truncated."""
    text = text[:CAPTION_MAX_CHARS] + ("…" if len(text) > CAPTION_MAX_CHARS else "")
    text = text.replace("'", "’")  # a real apostrophe glyph, not a drawtext escape issue
    for ch in ("\\", ":", ",", "%"):
        text = text.replace(ch, "\\" + ch)
    return text


def source_video(clip_id):
    web = OUT / clip_id / "web.mp4"
    if web.exists():
        return web
    raw = RAW / f"{clip_id}.mp4"
    return raw if raw.exists() else None


def _clip_window(t_start, t_end, duration_s):
    a, b = t_start - PAD_S, t_end + PAD_S
    if b - a < MIN_CLIP_S:
        mid = (a + b) / 2
        a, b = mid - MIN_CLIP_S / 2, mid + MIN_CLIP_S / 2
    if b - a > MAX_CLIP_S:
        b = a + MAX_CLIP_S
    return max(0.0, a), min(duration_s, b)


def select_friction_moments(clip_ids, max_clips):
    """Rank: root_cause findings first (clustered, strongest signal), then reattempt events, then
    the longest other friction events. One moment per (clip, rounded start) to avoid near-dupes."""
    moments, seen = [], set()

    for f in root_cause.analyse(clip_ids):
        tl = load(f["clip_id"])
        evs = [e for e in tl["events"] if e["step_id"] == f["step_id"] and e["type"] in ("reattempt", "extra_reach")]
        if not evs:
            continue
        a, b = min(e["t_start"] for e in evs), max(e["t_end"] for e in evs)
        key = (f["clip_id"], round(a))
        if key in seen:
            continue
        seen.add(key)
        moments.append({"clip_id": f["clip_id"], "t_start": a, "t_end": b, "rank": 0,
                        "caption": f"{f['step_label']}: {f['root_cause']}"})

    friction_rest = []
    for c in clip_ids:
        tl = load(c)
        for e in tl["events"]:
            if e["severity"] == "green" or e["type"] in ("collaboration", "possible_collaboration"):
                continue
            key = (c, round(e["t_start"]))
            if key in seen:
                continue
            friction_rest.append({"clip_id": c, "t_start": e["t_start"], "t_end": e["t_end"],
                                  "rank": 1, "caption": e["note"] or e["type"], "_dur": e["t_end"] - e["t_start"]})
    friction_rest.sort(key=lambda m: -m["_dur"])
    for m in friction_rest:
        key = (m["clip_id"], round(m["t_start"]))
        if key in seen:
            continue
        seen.add(key)
        moments.append(m)

    moments.sort(key=lambda m: m["rank"])
    return moments[:max_clips]


def select_clean_moments(clip_ids, max_clips):
    """The longest friction-free work steps across the selected clips -- "how it should look"."""
    moments = []
    for c in clip_ids:
        tl = load(c)
        friction_spans = [(e["t_start"], e["t_end"]) for e in tl["events"] if e["severity"] != "green"]
        for s in tl["steps"]:
            if s["duration_s"] < MIN_CLIP_S:
                continue
            if any(a < s["t_end"] and b > s["t_start"] for a, b in friction_spans):
                continue
            moments.append({"clip_id": c, "t_start": s["t_start"], "t_end": s["t_end"], "rank": 0,
                            "caption": f"{s['label']} -- clean, {s['duration_s']:.0f}s, no friction"})
    moments.sort(key=lambda m: -(m["t_end"] - m["t_start"]))
    return moments[:max_clips]


def build(clip_ids, out_path, mode="friction", max_clips=6):
    selector = select_clean_moments if mode == "clean" else select_friction_moments
    moments = selector(clip_ids, max_clips)
    font = _font()
    ff = imageio_ffmpeg.get_ffmpeg_exe()

    used, skipped = [], []
    tmp_dir = out_path.parent / f".{out_path.stem}_parts"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    parts = []
    for i, m in enumerate(moments):
        src = source_video(m["clip_id"])
        if src is None:
            skipped.append({**m, "reason": "no source video (outputs/<clip>/web.mp4 or data/raw/<clip>.mp4)"})
            continue
        duration_s = load(m["clip_id"])["duration_s"]
        a, b = _clip_window(m["t_start"], m["t_end"], duration_s)
        part = tmp_dir / f"{i:02d}.mp4"
        caption = _drawtext_escape(m["caption"])
        draw = (f"drawtext=text='{caption}':fontcolor=white:fontsize=22:box=1:boxcolor=black@0.55:"
                f"boxborderw=10:x=24:y=h-th-24" + (f":fontfile='{font}'" if font else ""))
        cmd = [ff, "-y", "-loglevel", "error", "-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", str(src),
               "-vf", draw, "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
               "-pix_fmt", "yuv420p", "-an", str(part)]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            skipped.append({**m, "reason": f"ffmpeg failed: {e.stderr.decode()[-300:]}"})
            continue
        parts.append(part)
        used.append({"clip_id": m["clip_id"], "t_start": round(m["t_start"], 1), "t_end": round(m["t_end"], 1),
                     "caption": m["caption"], "cite": f"[{m['clip_id']}@{fmt_t(m['t_start'])}]"})

    if not parts:
        for p in tmp_dir.glob("*"):
            p.unlink()
        tmp_dir.rmdir()
        return {"moments": [], "skipped": skipped, "out": None,
                "note": "No source video available for any selected moment (needs outputs/<clip>/web.mp4 "
                        "or data/raw/<clip>.mp4)."}

    concat_list = tmp_dir / "concat.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                    "-c", "copy", str(out_path)], check=True, capture_output=True)

    for p in parts:
        p.unlink()
    concat_list.unlink()
    tmp_dir.rmdir()

    return {"moments": used, "skipped": skipped, "out": str(out_path), "mode": mode,
            "duration_s": round(sum(m["t_end"] - m["t_start"] for m in used) + PAD_S * 2 * len(used), 1)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="+")
    ap.add_argument("--mode", choices=["friction", "clean"], default="friction")
    ap.add_argument("--max-clips", type=int, default=6)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = Path(a.out) if a.out else OUT / f"highlight_reel_{a.mode}.mp4"
    r = build(a.clips, out, a.mode, a.max_clips)
    print(json.dumps(r, indent=1))
