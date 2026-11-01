"""Tool segmentation mask (PS2's bonus list names "SAM 2 masks" specifically): given a step's
detected tool box (events/apply_tools.py's tool_detected_box, from perception/tools.py's
open-vocabulary detection) and that step's keyframe image, prompt a real SAM 2 model with the box
and save the resulting mask as a translucent overlay PNG on top of the keyframe.

Honesty note, same as the rest of the tool-detection chain: this runs SAM 2 tiny (the lightest
official checkpoint, CPU-feasible) per keyframe, not the full SAM 2 video predictor with memory
propagation across frames -- a still-image box-prompted mask, not a tracked video segmentation. And
it inherits the upstream box's own uncertainty: there is no labelled footage to measure end-to-end
mask IoU against, so every mask ships with the SAME "unvalidated" note as the box that seeded it.

Usage: python events/tool_mask.py <clip_id>
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"

NOTE = ("SAM 2 (tiny, CPU) mask from a single keyframe, box-prompted by the open-vocabulary tool "
        "detection -- not the full video predictor, and unvalidated like the box that seeded it.")
_model_cache = {}


def _load_model(weights="sam2_t.pt"):
    """Lazy import: ultralytics' SAM wrapper (and torch) are optional, heavy dependencies that most
    of this project never needs. Only import them if mask generation is actually requested."""
    if weights in _model_cache:
        return _model_cache[weights]
    from ultralytics import SAM
    m = SAM(weights)
    _model_cache[weights] = m
    return m


def _box_px(box, w, h):
    cx, cy, bw, bh = box["cx"] * w, box["cy"] * h, box["w"] * w, box["h"] * h
    return [cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2]


def generate(clip_id, weights="sam2_t.pt"):
    """Generates an overlay PNG per step that has a tool_detected_box and a saved keyframe. Returns
    a list of {step_id, tool, mask_path, note}."""
    tl_path = OUT / clip_id / "timeline.json"
    tl = json.loads(tl_path.read_text())
    frames_dir = OUT / clip_id / "frames"
    model = None
    results = []

    for step in tl["steps"]:
        box = step.get("tool_detected_box")
        kf = step.get("keyframe")
        if not box or not kf:
            continue
        img_path = OUT / clip_id / kf
        if not img_path.exists():
            continue
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        h, w = img.shape[:2]
        px = _box_px(box, w, h)
        model = model or _load_model(weights)
        res = model.predict(img, bboxes=[px], verbose=False)
        if not res or res[0].masks is None:
            continue
        mask = res[0].masks.data[0].cpu().numpy().astype(bool)

        overlay = img.copy()
        overlay[mask] = (overlay[mask] * 0.45 + np.array([40, 180, 255]) * 0.55).astype(np.uint8)
        cv2.rectangle(overlay, (int(px[0]), int(px[1])), (int(px[2]), int(px[3])), (40, 180, 255), 1)
        out_name = f"step{step['step_id']}_mask.jpg"
        cv2.imwrite(str(frames_dir / out_name), overlay, [cv2.IMWRITE_JPEG_QUALITY, 85])

        step["tool_mask"] = f"frames/{out_name}"
        step["tool_mask_note"] = NOTE
        results.append({"step_id": step["step_id"], "tool": step.get("tool_detected"),
                        "mask_path": step["tool_mask"], "note": NOTE})

    if results:
        tl_path.write_text(json.dumps(tl, indent=1))
    return results


if __name__ == "__main__":
    r = generate(sys.argv[1])
    print(json.dumps(r, indent=1))
