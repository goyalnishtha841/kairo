"""Package the processed sample recordings so the deployed site always has them.

Copies what the web app reads at runtime (timeline, hand tracks, keyframes, scores, reports) and a
smaller 640x360 copy of each playback video into one tar.gz. The archive is attached to a GitHub
Release and the Dockerfile unpacks it into outputs/ at build time, so the data is part of every
deploy and survives restarts (Render's free disk is wiped on each deploy).

The score caches are shipped too. Each records the mtimes of timeline.json and hands.json it was
computed from, so those mtimes are set to whole seconds (tar always keeps whole seconds) and the
cache stamps rewritten to match; on the server the caches are then valid as soon as the archive is
unpacked. Videos already encoded in <work dir> are reused unless --reencode is given.

Usage: python scripts/build_sample_data.py <work dir> [archive name] [--reencode]
"""
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
KEEP = ("timeline.json", "hands.json", "metrics.json", "social.json", "tools.json")
# score caches, shipped so the first visitor after a restart doesn't wait for them to be recomputed
CACHES = ("proficiency_metrics.json", "skill_features.json")
TOP = ("shift_report.json", "accuracy.json", "accuracy_heldout.json", "verification.json")


def main(work, name="kairo-sample-data-v1.tar.gz", reencode=False):
    work = Path(work)
    stage = work / "outputs"
    if reencode and stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True, exist_ok=True)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    clips = sorted(p.parent.name for p in OUT.glob("*/timeline.json") if not p.parent.name.startswith("zz-"))
    for c in clips:
        src, dst = OUT / c, stage / c
        dst.mkdir(exist_ok=True)
        for f in KEEP:
            if (src / f).exists():
                shutil.copy2(src / f, dst / f)
        stamp = []
        for f in ("timeline.json", "hands.json"):   # same order the caches use
            if (dst / f).exists():
                t = int((dst / f).stat().st_mtime)
                os.utime(dst / f, (t, t))
                stamp.append(float(t))
        for f in CACHES:
            if (src / f).exists():
                cache = json.loads((src / f).read_text())
                cache["stamp"] = stamp
                (dst / f).write_text(json.dumps(cache))
        if (src / "frames").exists() and not (dst / "frames").exists():
            shutil.copytree(src / "frames", dst / "frames")
        if (src / "web.mp4").exists() and (reencode or not (dst / "web.mp4").exists()):
            subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src / "web.mp4"), "-an",
                            "-vf", "scale=640:-2", "-c:v", "libx264", "-preset", "slow", "-crf", "32",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst / "web.mp4")], check=True)
        print(c, f"{sum(p.stat().st_size for p in dst.rglob('*') if p.is_file()) / 1e6:.1f} MB", flush=True)
    for f in TOP:
        if (OUT / f).exists():
            shutil.copy2(OUT / f, stage / f)
    archive = work / name
    with tarfile.open(archive, "w:gz", compresslevel=6) as tar:
        tar.add(stage, arcname="outputs")
    print(f"{archive} {archive.stat().st_size / 1e6:.1f} MB, {len(clips)} recordings")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(*args, reencode="--reencode" in sys.argv)
