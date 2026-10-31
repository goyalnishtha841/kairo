import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for sub in ("", "perception", "events", "ai"):
    sys.path.insert(0, str(ROOT / sub) if sub else str(ROOT))

RAW = ROOT / "data" / "raw"
OUT = ROOT / "outputs"
TEST_CLIP = "zz-e2e-test"          # sorted last so it never becomes the UI's default clip
SOURCE = "MTL-SGF00106-023"        # a clip where the worker's hands are often in view


def processed_clips():
    return sorted(p.parent.name for p in OUT.glob("*/timeline.json")
                  if not p.parent.name.startswith("zz-"))


@pytest.fixture(scope="session")
def source_video():
    p = RAW / f"{SOURCE}.mp4"
    if not p.exists():
        pytest.skip(f"{p.name} not downloaded")
    return p


@pytest.fixture(scope="session")
def e2e_clip(source_video):
    """Cut a 25 s test clip from real footage and run the whole pipeline on it."""
    import imageio_ffmpeg
    import pipeline

    dst = RAW / f"{TEST_CLIP}.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", "60", "-t", "25",
                    "-i", str(source_video), "-c", "copy", str(dst)], check=True)
    pipeline.process(TEST_CLIP, stride=2)
    yield TEST_CLIP
    dst.unlink(missing_ok=True)
    shutil.rmtree(OUT / TEST_CLIP, ignore_errors=True)


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from server.app import app
    return TestClient(app)


def load_tl(clip_id):
    return json.loads((OUT / clip_id / "timeline.json").read_text())
