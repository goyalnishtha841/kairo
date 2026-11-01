"""Package the processed sample recordings so the deployed site always has them.

Copies what the web app reads at runtime (timeline, hand tracks, keyframes, scores, reports) and a
smaller 640x360 copy of each playback video into one tar.gz. The archive is attached to a GitHub
Release and the Dockerfile unpacks it into outputs/ at build time, so the data is part of every
deploy and survives restarts (Render's free disk is wiped on each deploy).

Usage: python scripts/build_sample_data.py <work dir> [archive name]
"""
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
KEEP = ("timeline.json", "hands.json", "metrics.json", "social.json", "tools.json")
TOP = ("shift_report.json", "accuracy.json", "accuracy_heldout.json", "verification.json")


def main(work, name="kairo-sample-data-v1.tar.gz"):
    work = Path(work)
    stage = work / "outputs"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    clips = sorted(p.parent.name for p in OUT.glob("*/timeline.json") if not p.parent.name.startswith("zz-"))
    for c in clips:
        src, dst = OUT / c, stage / c
        dst.mkdir()
        for f in KEEP:
            if (src / f).exists():
                shutil.copy2(src / f, dst / f)
        if (src / "frames").exists():
            shutil.copytree(src / "frames", dst / "frames")
        if (src / "web.mp4").exists():
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
    main(*sys.argv[1:])
