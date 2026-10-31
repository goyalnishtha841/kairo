"""Recommendation engine v2: evidence records, confidence, ROI and simulation."""
import pytest

import config as C
import recommend


def ev(clip, t, dur):
    return {"clip_id": clip, "t": t, "dur": dur, "id": f"e{t}", "note": None}


def test_confidence_grows_with_evidence_and_spread():
    weak = recommend.confidence([3.0], 1, 10)
    strong = recommend.confidence([3.0] * 30, 8, 10)
    assert 0 <= weak < 0.4 < strong <= 1


def test_consistent_durations_beat_erratic_ones():
    steady = recommend.confidence([3, 3, 3, 3, 3, 3], 3, 3)
    erratic = recommend.confidence([0.5, 9, 1, 12, 0.5, 7], 3, 3)
    assert steady > erratic


def test_roi_formula():
    eur = recommend.roi_eur_per_year(60)  # one hour per shift
    assert eur == round(C.LABOR_EUR_PER_HOUR * C.SHIFTS_PER_DAY * C.WORKDAYS_PER_YEAR)


def test_build_produces_full_evidence_records_sorted_by_roi():
    evidence = {"search": [ev("a", i * 10, 2.0) for i in range(20)],
                "idle": [ev("b", 5, 4.0)]}
    recs = recommend.build(evidence, observed_s=600, n_clips=2, search_dirs={"left": 15, "right": 5})
    assert [r["friction_type"] for r in recs] == ["search", "idle"]
    r = recs[0]
    for key in ("observation", "action", "evidence_stats", "confidence", "confidence_method",
                "saving_min_per_shift", "roi_eur_per_year", "evidence"):
        assert key in r
    assert r["evidence_stats"]["events"] == 20 and r["evidence_stats"]["mean_s"] == 2.0
    assert "left" in r["observation"]
    # 20 x 2 s x 0.6 recoverable = 24 s in 600 s -> 8 h shift: 24 * 48 / 60 = 19.2 min
    assert r["saving_min_per_shift"] == pytest.approx(19.2, abs=0.1)
    assert len(r["evidence"]) <= 5


def test_simulation_removes_recoverable_share_and_shifts_time():
    tl = {"clip_id": "x", "duration_s": 30.0,
          "states": [{"state": "work", "t_start": 0, "t_end": 10}, {"state": "search", "t_start": 10, "t_end": 20},
                     {"state": "work", "t_start": 20, "t_end": 30}],
          "events": [{"type": "search", "t_start": 10, "t_end": 20}]}
    sim = recommend.simulate(tl, "search")
    assert sim["saved_s"] == pytest.approx(10 * C.RECOVERABLE["search"])
    assert sim["duration_after"] == pytest.approx(30 - sim["saved_s"])
    search_after = [s for s in sim["after"] if s["state"] == "search"][0]
    assert search_after["t_end"] - search_after["t_start"] == pytest.approx(10 * (1 - C.RECOVERABLE["search"]))
    assert sim["after"][-1]["t_end"] == pytest.approx(sim["duration_after"])


def test_simulate_api(client):
    import json
    from conftest import processed_clips
    clip = processed_clips()[0]
    r = client.get(f"/api/simulate?clip={clip}&friction_type=idle")
    assert r.status_code == 200 and r.json()["saved_s"] >= 0
    assert client.get(f"/api/simulate?clip={clip}&friction_type=nonsense").status_code == 400
