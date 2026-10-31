"""Unit test for USP 6: catching hidden inefficiencies — repeated pick/put-back/pick cycles.

Builds a synthetic hands.json where one hand settles on the same spot three times, with short
moves in between (pick / put back / pick again), and checks that events/timeline.py reports it
as a "reattempt" event rather than silently absorbing it into "work".
"""
import json
import shutil

import pytest

import timeline

CLIP = "zz-reattempt-test"


def xs_for_cycles(n_touches, touch_frames=4, move_frames=3):
    """x positions: a stall at 0.40, then an out-and-back move, repeated n_touches times."""
    stall = [0.40] * touch_frames
    out = list(__import__("numpy").linspace(0.40, 0.60, move_frames + 1)[1:])
    back = list(__import__("numpy").linspace(0.60, 0.40, move_frames + 1)[1:])
    xs = []
    for i in range(n_touches):
        xs += stall
        if i < n_touches - 1:
            xs += out + back
    return xs


def make_hands(clip_id, xs, dt=0.25, hand="R"):
    frames = []
    for i, x in enumerate(xs):
        frames.append({
            "t": round(i * dt, 3),
            "hands": [{"id": hand, "lm": [[x, 0.40, 0.0]] * 21, "bridged": False}],
            "cam": {"pan": 0.0, "tilt": 0.0},
        })
    data = {"fps": 1.0 / dt, "duration_s": round((len(xs) - 1) * dt, 3), "frames": frames}
    d = timeline.OUT / clip_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "hands.json").write_text(json.dumps(data))


@pytest.fixture
def clip():
    yield CLIP
    shutil.rmtree(timeline.OUT / CLIP, ignore_errors=True)


def test_repeated_pick_putback_is_reported_as_reattempt(clip):
    make_hands(clip, xs_for_cycles(3))
    tl = timeline.build(clip)
    reattempts = [e for e in tl["events"] if e["type"] == "reattempt"]
    assert reattempts, "three touches on the same spot should surface a reattempt event"
    ev = reattempts[0]
    assert ev["hand"] == "R"
    assert ev["severity"] == "yellow"
    assert "correction" in ev["note"]
    assert ev["step_id"] == 1


def test_a_single_settle_is_not_a_reattempt(clip):
    make_hands(clip, xs_for_cycles(1, touch_frames=12))
    tl = timeline.build(clip)
    assert not [e for e in tl["events"] if e["type"] == "reattempt"]


def test_two_touches_are_not_enough_either(clip):
    # a pick and a single correction (2 touches) is normal work, not the "hidden inefficiency" pattern
    make_hands(clip, xs_for_cycles(2))
    tl = timeline.build(clip)
    assert not [e for e in tl["events"] if e["type"] == "reattempt"]
