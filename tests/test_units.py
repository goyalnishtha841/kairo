"""Algorithm units: hand identity, ego-hand filter, One-Euro smoothing, head-motion estimation, API safety."""
import numpy as np
import pytest

import hands
from ego_motion import EgoMotion
from one_euro import OneEuro


def fake_hand(x, y, scale=0.1):
    lm = np.zeros((21, 3))
    lm[:, 0], lm[:, 1] = x, y
    lm[9, 1] = y - scale      # middle MCP above the wrist -> palm length = scale
    return lm


def test_identity_follows_position_not_flipped_label():
    ident = hands.HandIdentity()
    first = ident.assign([("L", .9, fake_hand(.3, .8)), ("R", .9, fake_hand(.7, .8))], 0.0)
    assert set(first) == {"L", "R"}
    # MediaPipe flips the labels for one frame, but the hands barely moved
    nxt = ident.assign([("R", .9, fake_hand(.31, .8)), ("L", .9, fake_hand(.69, .8))], 0.07)
    assert nxt["L"][1][0, 0] == pytest.approx(.31)
    assert nxt["R"][1][0, 0] == pytest.approx(.69)
    assert ident.label_overrides == 2


def test_identity_trusts_label_after_hand_was_lost():
    ident = hands.HandIdentity()
    ident.assign([("L", .9, fake_hand(.3, .8))], 0.0)
    out = ident.assign([("R", .9, fake_hand(.32, .8))], 2.0)   # long gap -> label wins
    assert "R" in out


def test_ego_labels_use_egocentric_geometry():
    # a hand low on the left whose fingers point up-right is the wearer's LEFT hand
    left = fake_hand(.3, .8)
    left[9, 0] = .36
    right = fake_hand(.7, .8)
    right[9, 0] = .64
    assert hands.ego_labels([left, right]) == ["L", "R"]
    assert hands.ego_labels([right, left]) == ["R", "L"]
    assert hands.ego_labels([left]) == ["L"] and hands.ego_labels([right]) == ["R"]


def test_ego_threshold_separates_near_and_far_hands():
    # palm length as a fraction of frame width (square frame here)
    near, far = 0.08, 0.02
    assert near >= hands.EGO_MIN_PALM > far


def test_one_euro_reduces_jitter_but_tracks_motion():
    rng = np.random.default_rng(0)
    t = np.arange(0, 4, 1 / 15)
    truth = np.where(t < 2, 0.3, 0.3 + 0.2 * (t - 2))          # still, then moving
    noisy = truth + rng.normal(0, 0.01, len(t))
    f = OneEuro()
    sm = np.array([f(np.array([v]), ti)[0] for v, ti in zip(noisy, t)])
    still = t < 2
    # >= 20% less jitter while still (real clips measure 27-39%)
    assert np.std(sm[still][5:]) < 0.8 * np.std(noisy[still][5:])
    assert abs(sm[-1] - truth[-1]) < 0.03                       # low lag when moving


def test_ego_motion_detects_pan_direction():
    rng = np.random.default_rng(1)
    img = (rng.random((360, 640)) * 255).astype(np.uint8)
    img = cv2_blur(img)
    em = EgoMotion(width=320)
    em(np_bgr(img), 1 / 15)
    shifted = np.roll(img, -12, axis=1)                          # scene moves left = head turns right
    out = em(np_bgr(shifted), 1 / 15)
    assert out["ok"] and out["pan"] < 0
    assert out["sharp"] > 0


def cv2_blur(img):
    import cv2
    return cv2.GaussianBlur(img, (5, 5), 1.5)


def np_bgr(gray):
    return np.dstack([gray] * 3)


def test_api_rejects_path_traversal_and_unknown_clips(client):
    assert client.get("/api/clips/..%2F..%2Fserver/timeline").status_code == 404
    assert client.get("/api/clips/does-not-exist/timeline").status_code == 404
    assert client.get("/media/does-not-exist/web.mp4").status_code == 404
    # the decoded path never reaches the process route (404 no clip / 405 no such route)
    assert client.post("/api/process/..%2Fetc").status_code in (404, 405)
    assert client.post("/api/process/not-a-clip").status_code == 404
    r = client.post("/api/upload", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_engine_endpoint(client):
    assert client.get("/api/engine").json()["engine"] in ("groq", "claude", "rules")
