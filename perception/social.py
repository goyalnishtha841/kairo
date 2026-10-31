"""Social signals for Collaboration Intelligence: other people, faces toward the wearer, voice activity.

A light second perception pass (2 frames per second + the audio track) so the expensive hand pass
is not repeated. Privacy: no audio, words or face images are stored; only per-window numbers.

Usage: python perception/social.py data/raw/<clip>.mp4      -> outputs/<clip>/social.json
"""
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import cv2
import imageio_ffmpeg
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
PERSON_MODEL = MODELS / "efficientdet_lite0.tflite"
FACE_MODEL = MODELS / "blaze_face_short_range.tflite"
URLS = {
    PERSON_MODEL: "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float16/latest/efficientdet_lite0.tflite",
    FACE_MODEL: "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite",
}
SAMPLE_HZ = 2.0          # analysis windows of 0.5 s
VAD_FRAME_MS = 30


def ensure_models():
    for path, url in URLS.items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(url, path)


def is_own_body(x0, y0, x1, y1):
    """The wearer's own legs/torso show up as a 'person' touching the bottom edge of a head camera."""
    return y1 > 0.95 and (y1 - y0) > 0.45


def frontal(kp, w):
    """Face roughly toward the camera: nose between the eyes and both eyes clearly apart."""
    (rex, rey), (lex, ley), (nx, ny) = kp[0], kp[1], kp[2]
    eye_d = abs(lex - rex)
    if eye_d < 0.25 * w:
        return False
    return abs(nx - (rex + lex) / 2) < 0.25 * eye_d


def head_face(frame, x0, y0, x1, y1, detector, size=256):
    """Face in the top part of a person box (full-res crop). Returns {width, frontal, score} or None."""
    H, W = frame.shape[:2]
    bw, bh = x1 - x0, y1 - y0
    cx0, cx1 = max(0, x0 - 0.1 * bw), min(1, x1 + 0.1 * bw)
    cy0, cy1 = max(0, y0 - 0.05 * bh), min(1, y0 + 0.45 * bh)
    crop = frame[int(cy0 * H):int(cy1 * H), int(cx0 * W):int(cx1 * W)]
    if crop.size == 0 or min(crop.shape[:2]) < 24:
        return None
    s = size / max(crop.shape[:2])
    crop = cv2.resize(crop, (int(crop.shape[1] * s), int(crop.shape[0] * s)))
    res = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)))
    if not res.detections:
        return None
    d = max(res.detections, key=lambda q: q.categories[0].score)
    kp = [(k.x, k.y) for k in d.keypoints]
    fw = d.bounding_box.width / crop.shape[1]
    return {"width": round(fw * (cx1 - cx0), 3), "frontal": bool(len(kp) >= 3 and frontal(kp, fw)),
            "score": round(d.categories[0].score, 2)}


def vad_windows(video, duration_s, win=1 / SAMPLE_HZ):
    """Share of 30 ms audio frames with voice activity, per analysis window (None if no audio)."""
    try:
        import webrtcvad
    except ImportError:
        return None
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
           "-f", "s16le", "-"]
    pcm = subprocess.run(cmd, capture_output=True).stdout
    if not pcm:
        return None
    vad = webrtcvad.Vad(3)  # most aggressive: fewer false "speech" in factory noise
    n = int(16000 * VAD_FRAME_MS / 1000) * 2
    flags = [vad.is_speech(pcm[i:i + n], 16000) for i in range(0, len(pcm) - n, n)]
    per_win = max(1, int(win * 1000 / VAD_FRAME_MS))
    n_win = int(np.ceil(duration_s / win))
    return [round(float(np.mean(flags[k * per_win:(k + 1) * per_win])), 2) if flags[k * per_win:(k + 1) * per_win]
            else 0.0 for k in range(n_win)]


def run(video, width=640):
    video = Path(video)
    ensure_models()
    out_dir = ROOT / "outputs" / video.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    persons = vision.ObjectDetector.create_from_options(vision.ObjectDetectorOptions(
        base_options=BaseOptions(model_asset_path=str(PERSON_MODEL)), score_threshold=0.45,
        category_allowlist=["person"], max_results=5))
    faces = vision.FaceDetector.create_from_options(vision.FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=str(FACE_MODEL)), min_detection_confidence=0.6))

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
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
        ppl, fcs = [], []
        for d in persons.detect(img).detections:
            b = d.bounding_box
            x0, y0, x1, y1 = b.origin_x / W, b.origin_y / H, (b.origin_x + b.width) / W, (b.origin_y + b.height) / H
            if is_own_body(x0, y0, x1, y1):
                continue
            ppl.append({"area": round((x1 - x0) * (y1 - y0), 3), "cx": round((x0 + x1) / 2, 2),
                        "score": round(d.categories[0].score, 2)})
            # The short-range face model needs a large face: look for it in the person's head region,
            # cropped from the full-resolution frame and upscaled.
            face = head_face(frame, x0, y0, x1, y1, faces)
            if face:
                fcs.append(face)
        samples.append({"t": round(idx / fps, 2), "persons": ppl, "faces": fcs})
        idx += 1
    cap.release()
    persons.close()
    faces.close()
    duration = n_total / fps
    social = {"clip_id": video.stem, "sample_hz": SAMPLE_HZ, "duration_s": round(duration, 2),
              "samples": samples, "speech": vad_windows(video, duration),
              "privacy": "No audio, words or face images stored: only per-window counts and ratios."}
    (out_dir / "social.json").write_text(json.dumps(social))
    return social


if __name__ == "__main__":
    s = run(sys.argv[1])
    n_p = sum(1 for x in s["samples"] if x["persons"])
    n_f = sum(1 for x in s["samples"] if any(f["frontal"] for f in x["faces"]))
    sp = s["speech"] or []
    print(f"{s['clip_id']}: {len(s['samples'])} samples, person in {n_p}, frontal face in {n_f}, "
          f"speech windows {sum(1 for v in sp if v >= 0.3)}/{len(sp)}")
