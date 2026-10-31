"""Every processed clip must honour the timeline contract (schema/timeline.md) and the insights math."""
import pytest

from conftest import load_tl, processed_clips

import insights

CLIPS = processed_clips()
TYPES = {"search", "transit", "idle", "hesitation", "extra_reach", "reattempt", "grasp", "release",
         "collaboration", "possible_collaboration",
         "tool_use", "step"}
STATES = {"work", "search", "transit", "idle"}
SEVERITY = {"search": "red", "transit": "red", "idle": "yellow", "hesitation": "yellow", "extra_reach": "yellow",
            "reattempt": "yellow", "collaboration": "blue", "possible_collaboration": "blue"}

pytestmark = pytest.mark.skipif(not CLIPS, reason="no processed clips")


@pytest.mark.parametrize("clip", CLIPS)
def test_timeline_schema(clip):
    tl = load_tl(clip)
    assert {"clip_id", "fps", "duration_s", "states", "steps", "events"} <= tl.keys()
    D = tl["duration_s"]
    for e in tl["events"]:
        assert e["type"] in TYPES
        assert 0 <= e["t_start"] <= e["t_end"] <= D + 0.5
        assert 0 <= e["confidence"] <= 1
        assert e["severity"] == SEVERITY.get(e["type"], "green")
    ids = [e["id"] for e in tl["events"]]
    assert len(ids) == len(set(ids)), "event ids must be unique"


@pytest.mark.parametrize("clip", CLIPS)
def test_states_are_contiguous_and_cover_clip(clip):
    tl = load_tl(clip)
    st = tl["states"]
    assert all(s["state"] in STATES for s in st)
    for a, b in zip(st, st[1:]):
        assert b["t_start"] >= a["t_end"] - 1e-6, "states overlap"
        assert b["t_start"] - a["t_end"] < 0.5, "gap between states"
        assert a["state"] != b["state"], "neighbouring states should be merged"
    covered = st[-1]["t_end"] - st[0]["t_start"]
    assert covered > 0.9 * tl["duration_s"]


@pytest.mark.parametrize("clip", CLIPS)
def test_steps_are_ordered_and_inside_work(clip):
    tl = load_tl(clip)
    steps = tl["steps"]
    assert [s["step_id"] for s in steps] == list(range(1, len(steps) + 1))
    for a, b in zip(steps, steps[1:]):
        assert b["t_start"] >= a["t_end"]
    for s in steps:
        assert s["duration_s"] >= 2.0 and s["label"]
        assert s["t_start"] <= s["keyframe_t"] <= s["t_end"]


def test_insights_math():
    r = insights.analyse(CLIPS)
    assert abs(sum(r["breakdown_pct"].values()) - 100) < 2
    assert r["lost_min_per_shift"] >= r["recoverable_min_per_shift"] >= 0
    savings = [x["saving_min_per_shift"] for x in r["recommendations"]]
    assert savings == sorted(savings, reverse=True)
    events = {(tl["clip_id"], e["id"]) for tl in map(load_tl, CLIPS) for e in tl["events"]}
    for rec in r["recommendations"]:
        assert rec["evidence"], "every recommendation needs evidence"
        for ev in rec["evidence"]:
            assert (ev["clip_id"], ev["id"]) in events, "evidence must point at a real event"
    if r["recommendations"]:
        assert r["headline"] and "min per" in r["headline"]


def test_extrapolation_scales_with_shift_length():
    a, b = insights.analyse(CLIPS, 8), insights.analyse(CLIPS, 4)
    if a["lost_min_per_shift"]:
        assert abs(a["lost_min_per_shift"] / b["lost_min_per_shift"] - 2) < 0.05
