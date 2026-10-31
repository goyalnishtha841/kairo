"""Smart Quality Score: explained 0-100 score per recording and per step, n/a when not measurable."""
import pytest

import copilot
import quality as Q
from conftest import processed_clips

CLIPS = processed_clips()
needs_data = pytest.mark.skipif(len(CLIPS) < 3, reason="needs several processed clips")


def station(c):
    return c.rsplit("-", 1)[0]


def busiest_station():
    by = {}
    for c in CLIPS:
        by.setdefault(station(c), []).append(c)
    return max(by.values(), key=len)


# ---------------------------------------------------------------- scoring rules
def test_ratio_points_full_up_to_ok_and_zero_from_bad():
    assert Q.ratio_points(1.0) == Q.ratio_points(Q.OK_AT) == 1.0
    assert Q.ratio_points(Q.BAD_AT) == Q.ratio_points(5) == 0.0
    assert 0 < Q.ratio_points((Q.OK_AT + Q.BAD_AT) / 2) < 1


def test_na_checks_are_left_out_and_score_renormalised():
    checks = {"sequence": {"status": "na", "reason": "x"}, "tools": {"status": "na", "reason": "x"},
              "time": {"frac": 1.0, "reason": "x"}, "movement": {"frac": 0.5, "reason": "x"},
              "flow": {"frac": 1.0, "reason": "x"}}
    total, rows, avail = Q._finish(checks)
    assert avail == Q.WEIGHTS["time"] + Q.WEIGHTS["movement"] + Q.WEIGHTS["flow"]
    assert total == round(100 * (25 + 10 + 15) / 60)
    assert [r["status"] for r in rows] == ["na", "na", "ok", "warn", "ok"]


def test_truncated_steps_are_not_timed():
    tl = {"duration_s": 60.0, "steps": [{"t_start": 0.0, "t_end": 10.0}, {"t_start": 12.0, "t_end": 20.0},
                                         {"t_start": 50.0, "t_end": 60.0}]}
    assert [s["t_start"] for s in Q.timed_steps(tl)] == [12.0]


def test_tools_check_needs_reference_and_captions():
    assert Q.check_tools(None)["status"] == "na"
    cmp = {"target": "x", "rows": [{"status": "match", "ref": {"label": "a", "tool": None},
                                    "target": {"label": "a", "tool": None, "t_start": 1}}]}
    assert Q.check_tools(cmp)["status"] == "na"
    cmp["rows"][0]["ref"]["tool"], cmp["rows"][0]["target"]["tool"] = "drill", "Hammer"
    r = Q.check_tools(cmp)
    assert r["frac"] == 0 and "Hammer instead of drill" in r["details"][0]


# ---------------------------------------------------------------- on the processed recordings
@pytest.fixture(scope="module")
def cache():
    return {}


@needs_data
def test_every_measured_point_has_a_reason(cache):
    for c in CLIPS:
        q = Q.score(c, None, cache)
        assert q["score"] is None or 0 <= q["score"] <= 100
        assert {k["check"] for k in q["checks"]} == set(Q.WEIGHTS)
        for k in q["checks"]:
            assert k["reason"]
            assert (k["points"] is None) == (k["status"] == "na")
        assert "not a person" in q["note"]
        for s in q["steps"]:
            assert 0 <= s["score"] <= 100 and s["reasons"]


@needs_data
def test_warnings_cite_timestamps(cache):
    for c in CLIPS:
        for k in Q.score(c, None, cache)["checks"]:
            if k["status"] in ("warn", "fail") and k["details"] and k["check"] != "sequence":
                assert all(f"[{c}@" in d for d in k["details"])
                return
    pytest.skip("no warning with details")


@needs_data
def test_reference_turns_on_sequence_and_self_reference_is_ignored(cache):
    clips = busiest_station()
    a, b = clips[0], clips[1]
    with_ref = {k["check"]: k for k in Q.score(a, b, cache)["checks"]}
    assert with_ref["sequence"]["status"] != "na"
    assert {k["check"]: k for k in Q.score(a, a, cache)["checks"]}["sequence"]["status"] == "na"


@needs_data
def test_more_idle_scores_lower_on_flow(cache):
    clips = busiest_station()
    flow = {c: Q._rate(Q._tl(c), Q.FLOW) for c in clips}
    worst, best = max(flow, key=flow.get), min(flow, key=flow.get)
    pts = lambda c: next(k for k in Q.score(c, None, cache)["checks"] if k["check"] == "flow")["points"]
    assert pts(worst) < pts(best)


@needs_data
def test_quality_api_and_copilot(client):
    c = CLIPS[0]
    r = client.get(f"/api/quality?clip={c}").json()
    assert r["clip_id"] == c and r["checks"] and r["station_scores"]
    assert client.get(f"/api/quality?clip={c}&ref=nope").status_code == 404
    ans = copilot.ask("Which recordings have the lowest quality score?", CLIPS, engine="rules")
    assert "Quality scores" in ans["answer"] and "not a person" in ans["answer"]
