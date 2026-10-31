"""Hand tracking core: MediaPipe HandLandmarker + stable L/R identity + One-Euro smoothing + metrics.

Usage:
    python perception/hands.py data/raw/<clip>.mp4 --stride 2 --max-seconds 60 --render

Writes outputs/<clip_id>/hands.json, metrics.json and (with --render) overlay.mp4.
"""
import argparse
import itertools
import json
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

from one_euro import OneEuro

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "hand_landmarker.task"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/latest/hand_landmarker.task")

HAND_IDS = ("L", "R")
LOST_RESET_S = 0.5      # reset a hand's filter after it's been missing this long
SWAP_GATE = 0.25        # max normalised wrist jump before we trust handedness over position
CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10),
               (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (0, 17),
               (17, 18), (18, 19), (19, 20)]


def ensure_model():
    if not MODEL_PATH.exists():
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        print("downloading hand_landmarker.task ...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)


def make_landmarker():
    ensure_model()
    opts = vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=2,
        min_hand_detection_confidence=0.4,
        min_hand_presence_confidence=0.4,
        min_tracking_confidence=0.5,
    )
    return vision.HandLandmarker.create_from_options(opts)


class HandIdentity:
    """Assigns detections to stable L/R ids.

    MediaPipe handedness assumes a mirrored (selfie) image; egocentric video is not mirrored,
    so labels are flipped. Position continuity wins over the label unless the hand jumped.
    """

    def __init__(self):
        self.last_wrist = {h: None for h in HAND_IDS}
        self.last_seen = {h: -1e9 for h in HAND_IDS}
        self.label_overrides = 0

    def assign(self, dets, t):
        # dets: list of (label 'L'/'R', score, lm ndarray 21x3)
        if not dets:
            return {}
        best, best_cost = None, 1e9
        for perm in itertools.permutations(HAND_IDS, len(dets)):
            cost = 0.0
            for (label, score, lm), hid in zip(dets, perm):
                prev = self.last_wrist[hid]
                recent = prev is not None and t - self.last_seen[hid] < LOST_RESET_S
                if recent:
                    d = float(np.linalg.norm(lm[0, :2] - prev))
                    cost += d if d < SWAP_GATE else SWAP_GATE + (0.0 if label == hid else 1.0)
                else:
                    cost += 0.0 if label == hid else 0.5
            if cost < best_cost:
                best, best_cost = perm, cost
        out = {}
        for (label, score, lm), hid in zip(dets, best):
            if label != hid:
                self.label_overrides += 1
            out[hid] = (score, lm)
            self.last_wrist[hid] = lm[0, :2].copy()
            self.last_seen[hid] = t
        return out


def jitter_px(seq, w, h):
    """Mean 2nd-difference magnitude (px) over consecutive frames of one hand — tremor-like noise."""
    if len(seq) < 3:
        return None
    a = np.array(seq)[:, :, :2] * [w, h]
    acc = a[2:] - 2 * a[1:-1] + a[:-2]
    return float(np.linalg.norm(acc, axis=-1).mean())


def draw(frame, hands):
    h, w = frame.shape[:2]
    colors = {"L": (255, 140, 0), "R": (0, 200, 255)}
    for hid, hd in hands.items():
        pts = (np.array(hd["lm"])[:, :2] * [w, h]).astype(int)
        for a, b in CONNECTIONS:
            cv2.line(frame, tuple(pts[a]), tuple(pts[b]), colors[hid], 2, cv2.LINE_AA)
        for p in pts:
            cv2.circle(frame, tuple(p), 3, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.putText(frame, f"{hid} {hd['score']:.2f}", tuple(pts[0] + [6, 18]),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, colors[hid], 2, cv2.LINE_AA)
    return frame


def run(video, stride=1, max_seconds=None, render=False, proc_width=640):
    video = Path(video)
    clip_id = video.stem
    out_dir = ROOT / "outputs" / clip_id
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W, H = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = min(1.0, proc_width / W)
    pw, ph = int(W * scale), int(H * scale)
    max_frames = int(max_seconds * fps) if max_seconds else n_total

    landmarker = make_landmarker()
    ident = HandIdentity()
    filters = {h: OneEuro() for h in HAND_IDS}
    writer = None
    if render:
        writer = cv2.VideoWriter(str(out_dir / "overlay.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
                                 fps / stride, (pw, ph))

    frames_out, raw_seq, smooth_seq = [], {h: [] for h in HAND_IDS}, {h: [] for h in HAND_IDS}
    n_proc = n_any = 0
    present = {h: 0 for h in HAND_IDS}
    scores = []
    t0 = time.perf_counter()

    idx = 0
    while idx < max_frames:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % stride:
            idx += 1
            continue
        t = idx / fps
        small = cv2.resize(frame, (pw, ph)) if scale < 1 else frame
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        res = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb),
                                          int(t * 1000))
        dets = []
        for lms, hd in zip(res.hand_landmarks, res.handedness):
            label = "R" if hd[0].category_name == "Left" else "L"  # un-mirror
            lm = np.array([[p.x, p.y, p.z] for p in lms])
            dets.append((label, hd[0].score, lm))

        assigned = ident.assign(dets, t)
        hands = {}
        for hid in HAND_IDS:
            if hid not in assigned:
                if t - ident.last_seen[hid] > LOST_RESET_S:
                    filters[hid].reset()
                    raw_seq[hid].append(None)
                    smooth_seq[hid].append(None)
                continue
            score, lm = assigned[hid]
            sm = filters[hid](lm, t)
            hands[hid] = {"score": round(float(score), 3), "lm": np.round(sm, 4).tolist(),
                          "lm_raw": np.round(lm[:, :2], 4).tolist()}
            raw_seq[hid].append(lm)
            smooth_seq[hid].append(sm)
            present[hid] += 1
            scores.append(score)

        n_proc += 1
        n_any += bool(hands)
        frames_out.append({"frame": idx, "t": round(t, 3),
                           "hands": [{"id": k, **v} for k, v in hands.items()]})
        if writer:
            writer.write(draw(small.copy(), hands))
        idx += 1

    elapsed = time.perf_counter() - t0
    cap.release()
    landmarker.close()
    if writer:
        writer.release()

    def runs(seq):  # contiguous non-None segments, for jitter
        cur, out = [], []
        for x in seq:
            if x is None:
                if len(cur) >= 3:
                    out.append(cur)
                cur = []
            else:
                cur.append(x)
        if len(cur) >= 3:
            out.append(cur)
        return out

    def mean_jitter(seqs):
        vals = [jitter_px(s, pw, ph) for h in HAND_IDS for s in runs(seqs[h])]
        vals = [v for v in vals if v is not None]
        return round(float(np.mean(vals)), 3) if vals else None

    j_raw, j_sm = mean_jitter(raw_seq), mean_jitter(smooth_seq)
    metrics = {
        "clip_id": clip_id,
        "video_fps": fps, "resolution": [W, H], "processed_resolution": [pw, ph],
        "stride": stride, "frames_processed": n_proc,
        "processing_fps": round(n_proc / elapsed, 2),
        "detection_rate_any_hand": round(n_any / max(n_proc, 1), 4),
        "presence_rate": {h: round(present[h] / max(n_proc, 1), 4) for h in HAND_IDS},
        "mean_confidence": round(float(np.mean(scores)), 4) if scores else None,
        "jitter_px_raw": j_raw, "jitter_px_smoothed": j_sm,
        "jitter_reduction_pct": round(100 * (1 - j_sm / j_raw), 1) if j_raw and j_sm else None,
        "label_overrides": ident.label_overrides,
    }
    (out_dir / "hands.json").write_text(json.dumps({"clip_id": clip_id, "fps": fps,
                                                    "frames": frames_out}))
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--stride", type=int, default=1, help="process every Nth frame")
    ap.add_argument("--max-seconds", type=float, default=None)
    ap.add_argument("--render", action="store_true", help="write overlay.mp4")
    ap.add_argument("--width", type=int, default=640, help="processing width")
    a = ap.parse_args()
    run(a.video, a.stride, a.max_seconds, a.render, a.width)
