"""Head (camera) motion from sparse optical flow between consecutive processed frames.

For a head-mounted camera, image-plane translation ~ head rotation (looking around),
in-plane rotation ~ head roll, and the residual flow spread ~ walking / body translation.
"""
import cv2
import numpy as np

_LK = dict(winSize=(21, 21), maxLevel=3,
           criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03))


class EgoMotion:
    def __init__(self, width=320):
        self.width = width
        self.prev = None

    def __call__(self, frame_bgr, dt):
        h, w = frame_bgr.shape[:2]
        s = self.width / w
        gray = cv2.cvtColor(cv2.resize(frame_bgr, (self.width, int(h * s))), cv2.COLOR_BGR2GRAY)
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        out = {"pan": 0.0, "tilt": 0.0, "roll": 0.0, "flow": 0.0, "sharp": round(sharp, 1), "ok": False}
        prev, self.prev = self.prev, gray
        if prev is None or dt <= 0:
            return out
        pts = cv2.goodFeaturesToTrack(prev, maxCorners=200, qualityLevel=0.01, minDistance=8)
        if pts is None or len(pts) < 12:
            return out
        nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, gray, pts, None, **_LK)
        good0, good1 = pts[st == 1], nxt[st == 1]
        if len(good0) < 12:
            return out
        M, inl = cv2.estimateAffinePartial2D(good0, good1, method=cv2.RANSAC, ransacReprojThreshold=2.0)
        if M is None:
            return out
        gw = gray.shape[1]
        # normalised by frame width per second, so values are resolution/fps independent
        out.update(
            pan=round(float(M[0, 2]) / gw / dt, 4),
            tilt=round(float(M[1, 2]) / gw / dt, 4),
            roll=round(float(np.arctan2(M[1, 0], M[0, 0])) / dt, 4),
            flow=round(float(np.median(np.linalg.norm(good1 - good0, axis=1))) / gw / dt, 4),
            ok=True,
        )
        return out
