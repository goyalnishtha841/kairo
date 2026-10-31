"""Temporal verification: flicker bridging, blip rejection, motion consistency, and its measured effect."""
import json

import numpy as np
import pytest

import timeline
import verify as V
from conftest import OUT, processed_clips

CLIPS = processed_clips()
FS = 15.0


def hand(x, y=0.5, score=0.95, size=0.1):
    """A flat 21-point hand whose palm centre is at (x, y) and whose wrist->middle-MCP length is `size`."""
    lm = np.zeros((21, 3))
    lm[:, 0], lm[:, 1] = x, y
    lm[0, 1] = y + size / 2 / V.ASPECT
    lm[9, 1] = y - size / 2 / V.ASPECT
    return {"id": "L", "score": score, "lm": lm.tolist(), "lm_raw": lm[:, :2].tolist()}


def frames(track):
    """track: per frame a hand dict or None -> hands.json-style frames."""
    return [{"frame": i, "t": i / FS, "hands": [h] if h else [], "cam": {"pan": 0, "tilt": 0, "ok": True}}
            for i, h in enumerate(track)]


def ids(fr):
    return ["L" if f["hands"] else "." for f in fr]


# ---------------------------------------------------------------- flicker
def test_one_frame_dropout_is_bridged_along_the_motion():
    """The screwdriver case: seen in frame 40, gone in 41, back in 42 -> stays stable."""
    track = [hand(0.3 + 0.01 * i) for i in range(5)] + [None] + [hand(0.3 + 0.01 * i) for i in range(6, 10)]
    out, st = V.verify_frames(frames(track))
    assert ids(out) == ["L"] * 10 and st["bridged"] == 1
    mid = out[5]["hands"][0]
    assert mid["bridged"] and abs(V._palm(mid["lm"])[0] - 0.35) < 1e-3   # interpolated on the path
    assert mid["score"] < min(track[4]["score"], track[6]["score"])
    assert st["flicker_after"] < st["flicker_before"]


def test_long_dropouts_are_not_bridged():
    gap = int(V.MAX_GAP_S * FS) + 3
    track = [hand(0.3)] * 5 + [None] * gap + [hand(0.3)] * 5
    out, st = V.verify_frames(frames(track))
    assert st["bridged"] == 0 and ids(out).count(".") == gap


def test_inconsistent_motion_is_not_bridged():
    """Reappearing far off the predicted path, or at a very different size, is a different object."""
    far = [hand(0.2)] * 5 + [None] + [hand(0.8)] * 5
    assert V.verify_frames(frames(far))[1]["bridged"] == 0
    resized = [hand(0.3, size=0.1)] * 5 + [None] + [hand(0.3, size=0.25)] * 5
    assert V.verify_frames(frames(resized))[1]["bridged"] == 0


def test_teleport_splits_a_track():
    seq = [hand(0.1)] * 3 + [hand(0.9)] * 3
    t = np.arange(6) / FS
    assert len(V.tracklets(seq, t)) == 2


# ---------------------------------------------------------------- false positives
def test_isolated_low_confidence_blip_is_rejected():
    track = [None] * 5 + [hand(0.5, score=0.5)] + [None] * 5
    out, st = V.verify_frames(frames(track))
    assert st["rejected"] == 1 and not any(f["hands"] for f in out)


def test_confident_or_repeated_short_detections_are_kept():
    """Measured on labels: brief appearances are usually real hands, so only weak one-frame blips go."""
    confident = [None] * 5 + [hand(0.5, score=0.9)] + [None] * 5
    assert V.verify_frames(frames(confident))[1]["rejected"] == 0
    two = [None] * 5 + [hand(0.5, score=0.5), hand(0.51, score=0.5)] + [None] * 5
    assert V.verify_frames(frames(two))[1]["rejected"] == 0


def test_bridged_frames_are_presence_not_motion():
    track = [hand(0.3 + 0.01 * i) for i in range(5)] + [None] + [hand(0.3 + 0.01 * i) for i in range(6, 10)]
    out, _ = V.verify_frames(frames(track))
    t, n_hands, _, _, pos, _ = timeline.load_signals({"frames": out})
    assert n_hands[5] == 1 and np.isnan(pos["L"][5, 0])


# ---------------------------------------------------------------- on the processed recordings
needs_data = pytest.mark.skipif(not CLIPS, reason="needs processed clips")


@needs_data
def test_verification_never_loses_more_than_it_rejects():
    fr = V.raw_frames(CLIPS[0])
    out, st = V.verify_frames(fr)
    assert st["detections_out"] == st["detections_in"] - st["rejected"] + st["bridged"]
    assert st["flicker_after"] <= st["flicker_before"]
    assert len(out) == len(fr) and [f["t"] for f in out] == [f["t"] for f in fr]


@needs_data
def test_raw_tracks_reproduce_the_saved_timeline(tmp_path, monkeypatch):
    """Verification is opt-in per clip: unverified tracks still give the timeline on disk."""
    clip = CLIPS[0]
    (tmp_path / clip).mkdir()
    (tmp_path / clip / "hands.json").write_text(json.dumps({**json.loads((OUT / clip / "hands.json").read_text()),
                                                            "frames": V.raw_frames(clip)}))
    monkeypatch.setattr(timeline, "OUT", tmp_path)
    saved = json.loads((OUT / clip / "timeline.json").read_text())
    if any(f["hands"] and f["hands"][0].get("bridged") for f in json.loads((OUT / clip / "hands.json").read_text())["frames"]):
        pytest.skip("this clip's saved timeline was built from verified tracks")
    assert timeline.build(clip)["states"] == saved["states"]


@pytest.mark.skipif(not (OUT.parent / "eval" / "heldout_labels.json").exists(), reason="needs labels")
def test_held_out_labels_improve_without_losing_precision():
    r = V.label_check("heldout_")
    assert r["rejected_detections"] == 0                       # no labelled real hand was rejected
    assert r["after"]["recall"] > r["before"]["recall"]
    assert r["after"]["precision"] >= r["before"]["precision"] - 0.02
    assert r["after"]["frame_presence"] >= r["before"]["frame_presence"]


def test_verification_api(client):
    r = client.get("/api/verification").json()
    assert r["total"]["flicker_after"] <= r["total"]["flicker_before"] and "clips" not in r
