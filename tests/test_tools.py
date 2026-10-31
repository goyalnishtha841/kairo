"""Unit tests for events/apply_tools.py: merging perception/tools.py's open-vocabulary detections
onto timeline.json steps. Builds synthetic tools.json/hands.json/timeline.json directly (bypassing
the actual YOLO-World model, the same way test_reattempt.py bypasses real video), since this module
is unvalidated against real footage and the test only needs to prove the merge logic, not the
detector's accuracy.
"""
import json
import shutil

import pytest

import apply_tools
from conftest import OUT

CLIP = "zzt-tools-test"


@pytest.fixture
def clip():
    d = OUT / CLIP
    d.mkdir(parents=True, exist_ok=True)
    yield CLIP
    shutil.rmtree(d, ignore_errors=True)


def write_inputs(clip_id, detections_near_hand, stray_detections=None):
    d = OUT / clip_id
    tl = {"clip_id": clip_id, "fps": 30.0, "duration_s": 10.0,
          "states": [{"state": "work", "t_start": 0, "t_end": 10}],
          "steps": [{"step_id": 1, "label": "Tighten screws", "t_start": 0, "t_end": 10, "duration_s": 10,
                     "hand": "R", "zone": "center", "active_ratio": 0.6, "keyframe_t": 5, "keyframe": None,
                     "tool": None}],
          "events": [], "signals": []}
    (d / "timeline.json").write_text(json.dumps(tl))

    frames = [{"t": round(i * 0.1, 2), "hands": [{"id": "R", "lm": [[0.5, 0.5, 0.0]] * 21, "bridged": False}],
               "cam": {}} for i in range(100)]
    (d / "hands.json").write_text(json.dumps({"fps": 10.0, "duration_s": 10.0, "frames": frames}))

    samples = []
    for i in range(20):
        dets = list(detections_near_hand) if i % 3 == 0 else []
        if stray_detections and i == 5:
            dets = dets + list(stray_detections)
        samples.append({"t": round(i * 0.5, 2), "detections": dets})
    (d / "tools.json").write_text(json.dumps({"clip_id": clip_id, "classes": ["screwdriver", "hammer"],
                                              "sample_hz": 2.0, "duration_s": 10.0, "samples": samples,
                                              "validated": False, "note": "test"}))


def test_picks_the_tool_detected_near_the_working_hand(clip):
    write_inputs(clip,
                 detections_near_hand=[{"label": "screwdriver", "score": 0.4, "cx": 0.51, "cy": 0.49,
                                        "w": 0.05, "h": 0.05}],
                 stray_detections=[{"label": "hammer", "score": 0.9, "cx": 0.02, "cy": 0.02, "w": 0.05, "h": 0.05}])
    n = apply_tools.apply(clip)
    tl = json.loads((OUT / clip / "timeline.json").read_text())
    assert n == 1
    step = tl["steps"][0]
    assert step["tool_detected"] == "screwdriver"
    assert step["tool_detected_confidence"] == 0.4
    assert "unvalidated" in step["tool_detection_note"]
    assert step["tool"] is None, "the VLM-captioned `tool` field must never be silently overwritten"


def test_no_detection_near_hand_leaves_tool_detected_null(clip):
    write_inputs(clip, detections_near_hand=[],
                 stray_detections=[{"label": "hammer", "score": 0.9, "cx": 0.02, "cy": 0.02, "w": 0.05, "h": 0.05}])
    apply_tools.apply(clip)
    tl = json.loads((OUT / clip / "timeline.json").read_text())
    step = tl["steps"][0]
    assert step["tool_detected"] is None
    assert step["tool_detected_confidence"] == 0.0
    assert step["tool_detection_note"] is None


def test_missing_tools_json_is_a_noop(clip):
    d = OUT / clip
    tl = {"clip_id": clip, "fps": 30.0, "duration_s": 10.0, "states": [], "steps": [], "events": [], "signals": []}
    (d / "timeline.json").write_text(json.dumps(tl))
    assert apply_tools.apply(clip) == 0
