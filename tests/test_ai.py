"""Copilot grounding (rules + Groq), citation hygiene, and the SOP comparator."""
import copy
import json
import os
import shutil

import pytest

from conftest import OUT, load_tl, processed_clips

import compare
import copilot

CLIPS = processed_clips()[:3]
QUESTIONS = [
    "Why is this workstation inefficient?",
    "Where did the worker search for tools?",
    "Which step took the longest?",
    "What should we change?",
    "When was the first idle period?",
    "Show me the steps",
]
pytestmark = pytest.mark.skipif(not CLIPS, reason="no processed clips")


def assert_citations_valid(ans):
    durations = {c: load_tl(c)["duration_s"] for c in CLIPS}
    for c in ans["citations"]:
        assert c["clip_id"] in durations, f"cited unknown clip {c}"
        assert 0 <= c["t"] <= durations[c["clip_id"]] + 1, f"cited time outside clip {c}"


@pytest.mark.parametrize("q", QUESTIONS)
def test_rules_copilot_answers_with_valid_citations(q):
    ans = copilot.ask(q, CLIPS, engine="rules")
    assert ans["engine"] == "rules" and len(ans["answer"]) > 20
    assert_citations_valid(ans)
    assert ans["citations"], f"no citations for: {q}"


def test_citation_normalisation():
    raw = "see [[A-1@00:04][A-1@00:39]] and 【A‑1@01:31】, not [a, b]"
    n = copilot.normalize(raw)
    assert [c["t"] for c in copilot.parse_citations(n)] == [4, 39, 91]
    assert "[a, b]" in n


@pytest.mark.skipif(not copilot.groq_available(), reason="no GROQ_API_KEY")
@pytest.mark.parametrize("q", QUESTIONS[:3])
def test_groq_copilot_is_grounded(q):
    ans = copilot.ask(q, CLIPS, engine="groq")
    if ans["engine"] != "groq":
        pytest.skip("Groq unreachable (fell back to rules)")
    assert_citations_valid(ans)


def test_compare_identical_clip_is_full_adherence():
    r = compare.compare(CLIPS[0], CLIPS[0])
    assert r["adherence_pct"] == 100
    assert r["counts"]["missing"] == r["counts"]["extra"] == r["counts"]["out_of_order"] == 0


@pytest.fixture
def synthetic_pair():
    """Reference with 4 named steps; target drops step 2, swaps 3 and 4, and makes step 1 slower."""
    base = load_tl(CLIPS[0])
    names = [("Cut panel with saw", "circular saw"), ("Inspect joint", None),
             ("Fasten slat with nail gun", "nail gun"), ("Sand edge", "sander")]
    ref = copy.deepcopy(base)
    ref["clip_id"], ref["steps"] = "zz-cmp-ref", []
    for i, (lab, tool) in enumerate(names):
        ref["steps"].append({"step_id": i + 1, "label": lab, "tool": tool, "t_start": i * 10.0,
                             "t_end": i * 10.0 + 8, "duration_s": 8.0, "keyframe_t": i * 10.0 + 4})
    tgt = copy.deepcopy(ref)
    tgt["clip_id"] = "zz-cmp-tgt"
    s1, _, s3, s4 = copy.deepcopy(ref["steps"])
    s1["duration_s"] = 16.0
    tgt["steps"] = [s1, s4, s3]
    for tl in (ref, tgt):
        (OUT / tl["clip_id"]).mkdir(exist_ok=True)
        (OUT / tl["clip_id"] / "timeline.json").write_text(json.dumps(tl))
    yield "zz-cmp-ref", "zz-cmp-tgt"
    for c in ("zz-cmp-ref", "zz-cmp-tgt"):
        shutil.rmtree(OUT / c, ignore_errors=True)


def test_compare_detects_missing_swapped_and_slower(synthetic_pair):
    r = compare.compare(*synthetic_pair)
    status = {(x["ref"] or {}).get("label"): x["status"] for x in r["rows"]}
    assert status["Inspect joint"] == "missing"
    assert status["Cut panel with saw"] == "slower"
    assert "out_of_order" in status.values()
    assert r["adherence_pct"] < 100
    assert any("Missing step" in f for f in r["findings"])


@pytest.mark.parametrize("q", ["Which recommendation has the highest ROI?", "Did the workflow deviate from baseline?"])
def test_rules_copilot_new_modules_cite_evidence(q):
    ans = copilot.ask(q, CLIPS, engine="rules")
    assert ans["citations"], q
    assert_citations_valid(ans)
    assert "worker is" not in ans["answer"].lower()  # workflow wording, never judging a person


def test_rules_copilot_collaboration_never_claims_content():
    ans = copilot.ask("When did collaboration occur?", CLIPS, engine="rules")
    assert_citations_valid(ans)
    low = ans["answer"].lower()
    assert "discussed" not in low and "they said" not in low


def test_collaboration_query_includes_possible_events():
    ctx = copilot.Context(CLIPS)
    both = ctx.events(type="collaboration", limit=500)
    assert all(e["type"] in copilot.COLLAB for e in both)
