"""Unit tests for events/highlight_reel.py: the auto-cut training montage. Builds tiny synthetic
videos with OpenCV (real frames, so ffmpeg has something to trim/caption/concat) and synthetic
timeline.json fixtures, then verifies the real ffmpeg pipeline produces a real, correctly-sized MP4.
"""
import json
import shutil

import cv2
import numpy as np
import pytest

import highlight_reel
from conftest import OUT

CLIPS = ["zzt-reel-001", "zzt-reel-002"]


def _write_video(clip_id, w=960, h=540, fps=10, n=200, shade=0):
    d = OUT / clip_id
    d.mkdir(parents=True, exist_ok=True)
    vw = cv2.VideoWriter(str(d / "web.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for _ in range(n):
        vw.write(np.full((h, w, 3), (20 + shade, 20, 20), dtype="uint8"))
    vw.release()


def _ev(id_, typ, a, b, step_id, note, severity="yellow"):
    return {"id": id_, "t_start": a, "t_end": b, "type": typ, "hand": "R", "tool": None, "zone": "right",
            "step_id": step_id, "cycle_id": None, "confidence": 0.5, "note": note, "severity": severity}


@pytest.fixture
def friction_clips():
    for i, c in enumerate(CLIPS):
        _write_video(c, shade=i * 40)
        tl = {"clip_id": c, "fps": 30.0, "duration_s": 20.0,
              "states": [{"state": "work", "t_start": 0, "t_end": 20}],
              "steps": [{"step_id": 1, "label": "Tighten screws", "t_start": 2, "t_end": 18, "duration_s": 16,
                         "hand": "R", "zone": "center", "active_ratio": 0.6, "keyframe_t": 10, "keyframe": None,
                         "tool": None}],
              "events": [
                  _ev("e1", "reattempt", 5, 8, 1, "3 grasp/release-like cycles in place (2 unnecessary corrections)"),
                  _ev("e2", "extra_reach", 9, 10.5, 1, "hand path 4x the straight line"),
              ], "signals": []}
        (OUT / c / "timeline.json").write_text(json.dumps(tl))
    yield CLIPS
    for c in CLIPS:
        shutil.rmtree(OUT / c, ignore_errors=True)


@pytest.fixture
def clean_clip():
    c = "zzt-reel-clean"
    _write_video(c)
    tl = {"clip_id": c, "fps": 30.0, "duration_s": 20.0,
          "states": [{"state": "work", "t_start": 0, "t_end": 20}],
          "steps": [{"step_id": 1, "label": "Open panel", "t_start": 2, "t_end": 8, "duration_s": 6,
                     "hand": "R", "zone": "center", "active_ratio": 0.6, "keyframe_t": 5, "keyframe": None,
                     "tool": None},
                    {"step_id": 2, "label": "Close panel", "t_start": 10, "t_end": 18, "duration_s": 8,
                     "hand": "R", "zone": "center", "active_ratio": 0.6, "keyframe_t": 14, "keyframe": None,
                     "tool": None}],
          "events": [], "signals": []}
    (OUT / c / "timeline.json").write_text(json.dumps(tl))
    yield [c]
    shutil.rmtree(OUT / c, ignore_errors=True)


def test_friction_mode_produces_a_real_captioned_video(friction_clips, tmp_path):
    out = tmp_path / "reel.mp4"
    r = highlight_reel.build(friction_clips, out, mode="friction", max_clips=4)
    assert out.exists() and out.stat().st_size > 1000
    assert out.read_bytes()[4:8] in (b"ftyp",)  # a real MP4 container, not an empty/corrupt file
    assert len(r["moments"]) == 4
    assert not r["skipped"]
    # root_cause's loose_fixture finding (reattempt+extra_reach cluster) ranks first
    assert "loose or missing fixture" in r["moments"][0]["caption"]
    assert all(m["cite"].startswith(f"[{m['clip_id']}@") for m in r["moments"])


def test_clean_mode_ranks_longer_friction_free_steps_first(clean_clip, tmp_path):
    out = tmp_path / "clean.mp4"
    r = highlight_reel.build(clean_clip, out, mode="clean", max_clips=2)
    assert out.exists() and out.stat().st_size > 1000
    assert len(r["moments"]) == 2
    assert r["moments"][0]["caption"].startswith("Close panel")  # 8s > 6s


def test_max_clips_is_respected(friction_clips, tmp_path):
    out = tmp_path / "reel.mp4"
    r = highlight_reel.build(friction_clips, out, mode="friction", max_clips=1)
    assert len(r["moments"]) == 1


def test_missing_source_video_is_reported_not_crashed(tmp_path):
    c = "zzt-reel-nosrc"
    d = OUT / c
    d.mkdir(parents=True, exist_ok=True)
    try:
        tl = {"clip_id": c, "fps": 30.0, "duration_s": 10.0,
              "states": [{"state": "work", "t_start": 0, "t_end": 10}],
              "steps": [{"step_id": 1, "label": "Step", "t_start": 0, "t_end": 10, "duration_s": 10,
                         "hand": "R", "zone": "center", "active_ratio": 0.6, "keyframe_t": 5, "keyframe": None,
                         "tool": None}],
              "events": [_ev("e1", "hesitation", 2, 4, 1, "hand stalled")], "signals": []}
        (d / "timeline.json").write_text(json.dumps(tl))
        out = tmp_path / "reel.mp4"
        r = highlight_reel.build([c], out, mode="friction", max_clips=4)
        assert r["out"] is None and not out.exists()
        assert r["skipped"] and "no source video" in r["skipped"][0]["reason"]
    finally:
        shutil.rmtree(d, ignore_errors=True)
