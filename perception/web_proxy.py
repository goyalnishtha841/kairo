"""Browser-playable proxy: HEVC source -> H.264 960px, no audio, fast-start (seekable).

Usage: python perception/web_proxy.py data/raw/<clip>.mp4
"""
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]


def make_proxy(video, width=960, force=False):
    video = Path(video)
    out = ROOT / "outputs" / video.stem / "web.mp4"
    if out.exists() and not force:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(video),
           "-vf", f"scale={width}:-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(out)]
    subprocess.run(cmd, check=True)
    return out


if __name__ == "__main__":
    print(make_proxy(sys.argv[1], force="--force" in sys.argv))
