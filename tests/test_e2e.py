"""End-to-end: real video -> perception -> timeline -> captions -> web proxy -> API -> UI."""
import json
import time

import cv2
import pytest

from conftest import OUT, RAW, load_tl


def test_pipeline_produces_all_artifacts(e2e_clip):
    d = OUT / e2e_clip
    for name in ("hands.json", "metrics.json", "timeline.json", "web.mp4"):
        assert (d / name).exists(), f"missing {name}"
    tl = load_tl(e2e_clip)
    assert 24 <= tl["duration_s"] <= 26
    assert tl["states"], "timeline has no activity states"


def test_hand_tracking_quality(e2e_clip):
    m = json.loads((OUT / e2e_clip / "metrics.json").read_text())
    assert m["frames_processed"] > 300                      # 25 s at 30 fps, stride 2
    assert m["detection_rate_any_hand"] > 0.2               # hands are in view in this segment
    assert m["mean_confidence"] > 0.7
    assert m["jitter_px_smoothed"] < m["jitter_px_raw"]     # One-Euro smoothing helps
    assert m["processing_fps"] > 5                          # usable on a laptop CPU


def test_hands_json_landmarks_are_valid(e2e_clip):
    h = json.loads((OUT / e2e_clip / "hands.json").read_text())
    seen = 0
    for f in h["frames"]:
        assert "cam" in f and "pan" in f["cam"]
        for hd in f["hands"]:
            assert hd["id"] in ("L", "R")
            assert len(hd["lm"]) == 21
            assert all(-0.2 <= c <= 1.2 for p in hd["lm"] for c in p[:2])
            seen += 1
        assert len({hd["id"] for hd in f["hands"]}) == len(f["hands"]), "duplicate hand id in a frame"
    assert seen > 0


def test_web_proxy_is_browser_playable(e2e_clip):
    cap = cv2.VideoCapture(str(OUT / e2e_clip / "web.mp4"))
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    codec = "".join(chr((fourcc >> 8 * i) & 255) for i in range(4))
    assert codec.lower() in ("avc1", "h264"), codec
    assert int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) == 960
    assert cap.read()[0]


def test_keyframes_written_for_steps(e2e_clip):
    tl = load_tl(e2e_clip)
    for s in tl["steps"]:
        assert s["keyframe"] and (OUT / e2e_clip / s["keyframe"]).exists()


def test_api_serves_new_clip_end_to_end(client, e2e_clip):
    ids = [c["clip_id"] for c in client.get("/api/clips").json()]
    assert e2e_clip in ids
    tl = client.get(f"/api/clips/{e2e_clip}/timeline").json()
    assert tl["clip_id"] == e2e_clip
    hands = client.get(f"/api/clips/{e2e_clip}/hands").json()
    assert hands["frames"] and len(hands["frames"][0]) == 2
    r = client.get(f"/media/{e2e_clip}/web.mp4", headers={"Range": "bytes=0-1023"})
    assert r.status_code == 206 and len(r.content) == 1024
    rep = client.get(f"/api/report?clips={e2e_clip}").json()
    assert rep["clips"] == [e2e_clip]
    ans = client.post("/api/ask", json={"question": "Which step took the longest?", "clips": [e2e_clip],
                                        "engine": "rules"}).json()
    assert ans["engine"] == "rules" and ans["answer"]


def test_ui_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "<div id=\"root\">" in r.text
    js = [l for l in r.text.split('"') if l.startswith("/assets/") and l.endswith(".js")]
    assert js and client.get(js[0]).status_code == 200


def test_upload_and_background_processing(client, source_video, tmp_path):
    """Upload a short video through the API and wait for the worker to process it."""
    import imageio_ffmpeg, subprocess, shutil
    src = tmp_path / "zz-upload-test.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", "10", "-t", "8",
                    "-i", str(source_video), "-c", "copy", str(src)], check=True)
    try:
        with src.open("rb") as f:
            job = client.post("/api/upload", files={"file": ("zz-upload-test.mp4", f, "video/mp4")}).json()
        assert job["state"] in ("queued", "running")
        deadline = time.time() + 240
        while time.time() < deadline:
            jobs = {j["clip_id"]: j for j in client.get("/api/jobs").json()}
            if jobs["zz-upload-test"]["state"] in ("done", "failed"):
                break
            time.sleep(2)
        assert jobs["zz-upload-test"]["state"] == "done", jobs["zz-upload-test"].get("error")
        assert "zz-upload-test" in [c["clip_id"] for c in client.get("/api/clips").json()]
        raw = {c["clip_id"]: c for c in client.get("/api/raw").json()}
        assert raw["zz-upload-test"]["processed"]
    finally:
        (RAW / "zz-upload-test.mp4").unlink(missing_ok=True)
        shutil.rmtree(OUT / "zz-upload-test", ignore_errors=True)
