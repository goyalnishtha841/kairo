"""Workflow Proficiency Engine: baselines, explainable scores, workflow-not-person wording."""
import statistics

import pytest

import config as C
import proficiency as P
from conftest import processed_clips

CLIPS = processed_clips()
pytestmark = pytest.mark.skipif(len(CLIPS) < 3, reason="needs several processed clips")


@pytest.fixture(scope="module")
def cache():
    return {}


def test_baseline_is_leave_one_out_and_same_station(cache):
    clip = CLIPS[0]
    b = P.baseline(clip, cache)
    assert clip not in b["recordings"]
    if b["scope"] == "station":
        assert all(P.station_of(c) == P.station_of(clip) for c in b["recordings"])
    assert b["reliability"] in ("high", "medium", "low")


def test_every_point_is_explained(cache):
    r = P.score(CLIPS[0], cache)
    assert 0 <= r["score"] <= 100
    assert r["metrics"] and all(m["explanation"] and m["label"] in m["explanation"] for m in r["metrics"])
    assert set(r["fingerprint"]) == {m["label"] for m in r["metrics"]}
    assert "not a person" in r["level_note"]


def test_worse_than_baseline_metrics_carry_timestamps(cache):
    for clip in CLIPS:
        r = P.score(clip, cache)
        for m in r["metrics"]:
            if m["direction"] == "worse" and m["metric"] in P.EVIDENCE_TYPE:
                assert m["evidence"] and all(e.startswith(f"[{clip}@") for e in m["evidence"])
                return
    pytest.skip("no clip is worse than baseline on an evidence-backed metric")


def test_station_median_workflow_scores_near_fifty(cache):
    scores = [P.score(c, cache)["score"] for c in CLIPS]
    assert 35 <= statistics.median(scores) <= 65


def test_more_friction_scores_lower(cache):
    """Within a station, the recording with the most search+idle time should not outscore the one with the least."""
    by_station = {}
    for c in CLIPS:
        by_station.setdefault(P.station_of(c), []).append(c)
    station = max(by_station, key=lambda s: len(by_station[s]))
    clips = by_station[station]
    friction = {c: P.metrics(c)["search_s_per_min"] + P.metrics(c)["idle_s_per_min"] for c in clips}
    worst, best = max(friction, key=friction.get), min(friction, key=friction.get)
    assert P.score(worst, cache)["score"] < P.score(best, cache)["score"]


def test_levels_follow_configured_thresholds():
    assert P.level(C.PROFICIENCY_ADVANCED) == "Advanced"
    assert P.level(C.PROFICIENCY_NEEDS_TRAINING) == "Intermediate"
    assert P.level(C.PROFICIENCY_NEEDS_TRAINING - 1) == "Needs training"


def test_proficiency_api(client):
    r = client.get(f"/api/proficiency?clip={CLIPS[0]}").json()
    assert r["clip_id"] == CLIPS[0] and r["curve"] and r["fingerprint"]
