"""Unit tests for USPs 7-20: SOP compliance, attention, search, digital twin, safety, collaboration
score, behaviour drift / adaptive baseline, root cause, knowledge graph, memory, and shift summary.

Builds a synthetic 3-clip station series directly as timeline.json (bypassing the perception
pipeline, like test_recommend.py/test_contracts.py do for their own units) so these tests run without
downloaded footage.
"""
import json
import shutil

import pytest

import attention
import baseline_drift
import collab_score
import config as C
import digital_twin
import insights
import knowledge_graph
import memory
import root_cause
import safety
import shift_summary
import sop
import search
from conftest import OUT

STATION = "zzt-usp"
CLIPS = [f"{STATION}-{i:03d}" for i in (1, 2, 3)]


def _step(sid, label, a, b, hand="R", zone="center"):
    return {"step_id": sid, "label": label, "t_start": a, "t_end": b, "duration_s": b - a, "hand": hand,
            "zone": zone, "active_ratio": 0.6, "keyframe_t": (a + b) / 2, "keyframe": None}


def _ev(typ, a, b, step_id=None, zone=None, hand="R", conf=0.6, note="", extra=None):
    sev = {"search": "red", "transit": "red", "idle": "yellow", "hesitation": "yellow",
           "extra_reach": "yellow", "reattempt": "yellow",
           "collaboration": "blue", "possible_collaboration": "blue"}.get(typ, "green")
    e = {"id": f"e{a}", "t_start": a, "t_end": b, "type": typ, "hand": hand, "tool": None, "zone": zone,
         "step_id": step_id, "cycle_id": None, "confidence": conf, "note": note, "severity": sev}
    if extra:
        e.update(extra)
    return e


def _write(clip_id, duration, steps, events, states):
    d = OUT / clip_id
    d.mkdir(parents=True, exist_ok=True)
    tl = {"clip_id": clip_id, "fps": 30.0, "duration_s": duration, "states": states, "steps": steps,
          "events": events, "signals": []}
    (d / "timeline.json").write_text(json.dumps(tl, indent=1))


@pytest.fixture(scope="module")
def clips():
    collab_evidence = {"signal_share": {"present": 0.9, "near": 0.8, "facing": 0.9, "speech": 0.7, "paused": 0.8},
                        "work_resumes": True}
    _write(CLIPS[0], 60.0,
           [_step(1, "Open panel", 0, 10), _step(2, "Disconnect power", 10, 20),
            _step(3, "Remove screw", 20, 30), _step(4, "Inspect", 30, 40), _step(5, "Close panel", 40, 50)],
           [_ev("search", 50, 53, step_id=5, zone="left", note="hands out of view, head scanning left")],
           [{"state": "work", "t_start": 0, "t_end": 50}, {"state": "search", "t_start": 50, "t_end": 53},
            {"state": "work", "t_start": 53, "t_end": 60}])
    _write(CLIPS[1], 95.0,
           [_step(1, "Open panel", 0, 10), _step(2, "Disconnect power", 10, 20),
            _step(3, "Remove screw", 20, 45), _step(4, "Close panel", 75, 85)],
           [_ev("reattempt", 25, 28, step_id=3, zone="right", note="3 grasp/release-like cycles in place"),
            _ev("extra_reach", 30, 32, step_id=3, zone="right", note="hand path 4x the straight line"),
            _ev("extra_reach", 33, 35, step_id=3, zone="right", note="hand path 5x the straight line"),
            _ev("search", 85, 92, step_id=4, zone="right", note="hands out of view, head scanning right"),
            _ev("collaboration", 45, 55, conf=0.95, hand=None,
                note="A collaboration event (10s): signals agree on near, facing, speech, paused",
                extra={"evidence": collab_evidence})],
           [{"state": "work", "t_start": 0, "t_end": 45}, {"state": "idle", "t_start": 45, "t_end": 55},
            {"state": "work", "t_start": 55, "t_end": 85}, {"state": "search", "t_start": 85, "t_end": 92},
            {"state": "work", "t_start": 92, "t_end": 95}])
    _write(CLIPS[2], 58.0,
           [_step(1, "Open panel", 0, 9), _step(2, "Disconnect power", 9, 18),
            _step(3, "Remove screw", 18, 28), _step(4, "Inspect", 28, 38), _step(5, "Close panel", 38, 48)],
           [_ev("hesitation", 48, 50, step_id=5, note="hand stalled 2.0s between movements")],
           [{"state": "work", "t_start": 0, "t_end": 58}])
    C.UNSAFE_ZONES[STATION] = ["right"]
    yield CLIPS
    C.UNSAFE_ZONES.pop(STATION, None)
    for c in CLIPS:
        shutil.rmtree(OUT / c, ignore_errors=True)


def test_sop_compliance_flags_missing_mandatory_step(clips):
    r = sop.check(clips[1], ["Open panel", "Disconnect power", "Remove screw", "Inspect", "Close panel"],
                  mandatory=["Inspect"])
    assert not r["compliant"]
    assert r["skipped_mandatory"] == ["Inspect"]
    assert r["missing_count"] == 1


def test_sop_compliance_clean_run_is_compliant(clips):
    r = sop.check(clips[0], ["Open panel", "Disconnect power", "Remove screw", "Inspect", "Close panel"],
                  mandatory=["Inspect"])
    assert r["compliant"]
    assert r["headline"] == "SOP followed in full."


def test_productivity_reasons_are_ranked_by_seconds_lost(clips):
    report = insights.analyse(clips)
    reasons = report["lost_time_reasons"]
    assert reasons == sorted(reasons, key=lambda r: -r["seconds"])
    assert "Lost time breakdown" in report["productivity_explanation"]


def test_attention_heatmap_sums_to_the_clip_duration(clips):
    hm = attention.heatmap(clips[1])
    assert abs(sum(hm["pct"].values()) - 100) < 1
    assert hm["pct"]["colleague"] > 0
    assert hm["not_detected"] == ["phone"]


def test_search_finds_collaboration_as_a_help_proxy(clips):
    r = search.search("show clips where workers asked for help", clips)
    assert r["count"] >= 1
    assert any("collaboration" in n for n in r["proxy_notes"])


def test_search_matches_step_label_text(clips):
    r = search.search("remove screw", clips)
    assert any(h["type"] == "step" and "screw" in h["note"].lower() for h in r["hits"])


def test_digital_twin_is_chronological_and_cites_evidence(clips):
    dt_ = digital_twin.narrate(clips[1])
    ts = [e["t"] for e in dt_["timeline"]]
    assert ts == sorted(ts)
    assert dt_["timeline"][0]["event"] == "Started" and dt_["timeline"][-1]["event"] == "Finished"
    assert all(e["cite"].startswith(f"[{clips[1]}@") for e in dt_["timeline"])


def test_safety_forecasts_only_when_a_zone_is_configured(clips):
    configured = safety.predict(clips[1])
    assert configured["configured"] and configured["forecasts"]
    assert 0 < configured["forecasts"][0]["probability_next_window"] <= 0.95

    C.UNSAFE_ZONES.pop(STATION)
    try:
        unconfigured = safety.predict(clips[1])
        assert not unconfigured["configured"] and unconfigured["forecasts"] == []
    finally:
        C.UNSAFE_ZONES[STATION] = ["right"]


def test_collaboration_score_counts_events_without_ranking_a_person(clips):
    cs = collab_score.shift_score(clips)
    assert cs["total_collaboration_events"] == 1
    assert cs["clip_with_most_waiting"] == clips[1]
    assert "never ranks a person" in cs["note"]


def test_drift_flags_the_slower_clip_and_names_grown_friction(clips):
    d = baseline_drift.drift(clips[1])
    assert d["drifted"] and d["change_pct"] < 0
    assert "search" in d["grown_friction"]


def test_adaptive_baseline_has_nothing_to_compare_for_the_first_clip(clips):
    a = baseline_drift.adaptive_score(clips[0])
    assert a["prior_clips"] == [] and a["change_pct"] is None


def test_root_cause_matches_the_loose_fixture_pattern(clips):
    findings = root_cause.analyse(clips)
    assert findings and findings[0]["pattern"] == "loose_fixture"
    assert findings[0]["step_label"] == "Remove screw"
    assert len(findings[0]["evidence"]) >= 1


def test_knowledge_graph_answers_task_delay_but_not_tool_when_unconfigured(clips):
    task_q = knowledge_graph.query("which task causes the highest delay?", clips)
    tool_q = knowledge_graph.query("which tool causes the highest delay?", clips)
    assert task_q["rows"]
    assert tool_q["rows"] == [] and "tool detection configured" in tool_q["answer"]


def test_knowledge_graph_answers_tool_delay_once_tools_are_detected(clips):
    # simulate a step having gone through perception/tools.py + events/apply_tools.py
    tl_path = OUT / clips[1] / "timeline.json"
    tl = json.loads(tl_path.read_text())
    tl["steps"][2]["tool_detected"] = "screwdriver"
    tl["steps"][2]["tool_detected_confidence"] = 0.42
    tl_path.write_text(json.dumps(tl))
    try:
        tool_q = knowledge_graph.query("which tool causes the highest delay?", clips)
        assert tool_q["rows"] and tool_q["rows"][0]["key"] == "screwdriver"
        assert "unvalidated" in tool_q["answer"]
    finally:
        del tl["steps"][2]["tool_detected"]
        del tl["steps"][2]["tool_detected_confidence"]
        tl_path.write_text(json.dumps(tl))


def test_memory_recognises_an_earlier_completed_step(clips):
    done = memory.already_done("inspect", clips)
    not_done = memory.already_done("tighten bolt four", clips)
    assert done["already_done"] and not not_done["already_done"]


def test_memory_ignores_steps_after_the_cutoff(clips):
    # "Close panel" in clip 3 happens after t=38 in that clip; asking before t=20 in clip 1 must not
    # see anything from later clips or later in clip 1 itself
    r = memory.already_done("close panel", clips, before_clip=clips[0], before_t=20)
    assert not r["already_done"]


def test_shift_summary_ties_the_other_usps_together(clips):
    sop_results = [sop.check(clips[1], ["Open panel", "Disconnect power", "Remove screw", "Inspect",
                                         "Close panel"], mandatory=["Inspect"])]
    s = shift_summary.summarize(clips, sop_results=sop_results)
    assert s["assemblies"] == 3
    assert s["quality_deviations"] == 1
    assert s["conversations"] == 1
    assert s["probable_safety_events"] >= 1
    assert "Today's shift" in s["narrative"]
