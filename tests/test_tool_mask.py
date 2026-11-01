"""Unit tests for events/tool_mask.py: real SAM 2 (tiny, CPU) box-prompted segmentation on a
synthetic keyframe. Not mocked -- loads the real model and runs real inference, same as
test_highlight_reel.py runs real ffmpeg, since the point is proving the pipeline mechanics work,
not just that functions get called.
"""
import json
import shutil

import cv2
import numpy as np
import pytest

import tool_mask
from conftest import OUT

CLIP = "zzt-mask-test"


@pytest.fixture
def clip_with_tool_box():
    d = OUT / CLIP
    (d / "frames").mkdir(parents=True, exist_ok=True)
    img = np.full((360, 640, 3), 30, dtype="uint8")
    cv2.rectangle(img, (260, 150), (380, 230), (200, 200, 220), -1)  # a bright, easy-to-segment blob
    cv2.imwrite(str(d / "frames" / "step1.jpg"), img)
    tl = {"clip_id": CLIP, "fps": 30.0, "duration_s": 10.0, "states": [], "events": [], "signals": [],
          "steps": [{"step_id": 1, "label": "Tighten screws", "t_start": 0, "t_end": 10, "duration_s": 10,
                     "hand": "R", "zone": "center", "active_ratio": 0.6, "keyframe_t": 5,
                     "keyframe": "frames/step1.jpg", "tool": None, "tool_detected": "screwdriver",
                     "tool_detected_confidence": 0.5, "tool_detection_note": "test",
                     "tool_detected_box": {"cx": 320 / 640, "cy": 190 / 360, "w": 120 / 640, "h": 80 / 360}}]}
    (d / "timeline.json").write_text(json.dumps(tl))
    yield CLIP
    shutil.rmtree(d, ignore_errors=True)


def test_generates_a_real_mask_overlay(clip_with_tool_box):
    results = tool_mask.generate(clip_with_tool_box)
    assert len(results) == 1
    r = results[0]
    assert r["step_id"] == 1 and r["tool"] == "screwdriver"
    mask_path = OUT / clip_with_tool_box / r["mask_path"]
    assert mask_path.exists() and mask_path.stat().st_size > 500
    assert "unvalidated" in r["note"]

    tl = json.loads((OUT / clip_with_tool_box / "timeline.json").read_text())
    step = tl["steps"][0]
    assert step["tool_mask"] == r["mask_path"]
    assert step["tool_mask_note"] == r["note"]


def test_skips_steps_without_a_tool_box():
    d = OUT / "zzt-mask-notool"
    d.mkdir(parents=True, exist_ok=True)
    try:
        tl = {"clip_id": "zzt-mask-notool", "fps": 30.0, "duration_s": 10.0, "states": [], "events": [],
              "signals": [], "steps": [{"step_id": 1, "label": "Step", "t_start": 0, "t_end": 10,
                                        "duration_s": 10, "hand": "R", "zone": "center", "active_ratio": 0.6,
                                        "keyframe_t": 5, "keyframe": None, "tool": None,
                                        "tool_detected": None, "tool_detected_confidence": 0.0,
                                        "tool_detection_note": None, "tool_detected_box": None}]}
        (d / "timeline.json").write_text(json.dumps(tl))
        assert tool_mask.generate("zzt-mask-notool") == []
    finally:
        shutil.rmtree(d, ignore_errors=True)
