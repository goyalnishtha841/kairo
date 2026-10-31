"""Tool detector (USP 4 / original pitch's YOLO-World module): open-vocabulary object detection
over a station's own tool list, so events can carry a real `tool` field instead of only a VLM guess
from one keyframe.

Honesty note (read before using this for anything beyond a demo): there is no labelled footage in
this repo to measure precision/recall against, unlike perception/hands.py's held-out accuracy numbers
(docs/TESTING.md). This module is present and functional -- it loads real weights and runs real
inference -- but its detections are UNVALIDATED. Never present its output with the confidence the
hand tracker earns; eval/tools_accuracy.py (stub) is where that validation should go once labelled
clips exist.

Usage: python perception/tools.py data/raw/<clip>.mp4 screwdriver hammer drill bolt wrench
    -> outputs/<clip>/tools.json
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_HZ = 2.0          # same cadence as perception/social.py: a light second pass, not the full 15 FPS hand pass
CONF_MIN = 0.15          # YOLO-World's open-vocabulary confidences run lower than closed-set detectors; kept low
                          # and left to the caller (events/apply_tools.py) to threshold per use, not silently dropped here
_model_cache = {}


def _load_model(weights="yolov8s-world.pt"):
    """Lazy import: ultralytics (and its CLIP text encoder) are optional, multi-hundred-MB
    dependencies that most of this project never needs. Only import them if tool detection is
    actually requested."""
    if weights in _model_cache:
        return _model_cache[weights]
    from ultralytics import YOLO
    m = YOLO(weights)
    _model_cache[weights] = m
    return m


def run(video, classes, width=640, weights="yolov8s-world.pt"):
    """classes: the station's own tool vocabulary (open-vocabulary text prompts, e.g.
    ["screwdriver", "hammer", "drill", "bolt", "wrench"]). No default list is supplied: a detector
    run on classes nobody asked for is exactly the kind of fabricated feature this project avoids."""
    if not classes:
        raise ValueError("tool detection needs a station tool vocabulary (events/config.py STATION_TOOLS)")
    video = Path(video)
    out_dir = ROOT / "outputs" / video.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    model = _load_model(weights)
    model.set_classes(list(classes))

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    every = max(1, int(round(fps / SAMPLE_HZ)))
    samples = []
    idx = 0
    while True:
        if idx % every:
            if not cap.grab():
                break
            idx += 1
            continue
        ok, frame = cap.read()
        if not ok:
            break
        h0, w0 = frame.shape[:2]
        small = cv2.resize(frame, (width, int(h0 * width / w0)))
        H, W = small.shape[:2]
        res = model.predict(small, verbose=False)[0]
        dets = []
        for box, cls, conf in zip(res.boxes.xyxy.tolist(), res.boxes.cls.tolist(), res.boxes.conf.tolist()):
            x0, y0, x1, y1 = box
            dets.append({"label": model.names[int(cls)], "score": round(float(conf), 3),
                         "cx": round((x0 + x1) / 2 / W, 3), "cy": round((y0 + y1) / 2 / H, 3),
                         "w": round((x1 - x0) / W, 3), "h": round((y1 - y0) / H, 3)})
        samples.append({"t": round(idx / fps, 2), "detections": dets})
        idx += 1
    cap.release()
    duration = n_total / fps

    data = {"clip_id": video.stem, "classes": list(classes), "sample_hz": SAMPLE_HZ,
            "duration_s": round(duration, 2), "samples": samples,
            "validated": False,
            "note": "Open-vocabulary detections (YOLO-World), unvalidated: no labelled footage exists "
                    "in this repo to measure precision/recall against."}
    (out_dir / "tools.json").write_text(json.dumps(data))
    return data


if __name__ == "__main__":
    s = run(sys.argv[1], sys.argv[2:])
    n_hit = sum(1 for x in s["samples"] if x["detections"])
    print(f"{s['clip_id']}: {len(s['samples'])} samples, detections in {n_hit}, classes {s['classes']}")
