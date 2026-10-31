"""Collaboration Intelligence must be precision-first: these scenarios encode the false positives we refuse."""
import json

import pytest

import collaboration as CO
import config as C

D = 60.0  # seconds per synthetic clip
N = int(D / CO.WIN)


def make(person=(), near=(), facing=(), speech=(), work=None, speech_level=None):
    """Build social + timeline dicts. Each arg is a list of (t0, t1) spans in seconds.
    work: spans where the wearer works (default: works the whole clip)."""
    def on(spans, t):
        return any(a <= t < b for a, b in spans)

    samples = []
    for k in range(N):
        t = k * CO.WIN
        persons, faces = [], []
        if on(person, t) or on(near, t) or on(facing, t):
            persons.append({"area": 0.15 if on(near, t) or on(facing, t) else 0.03, "cx": 0.5, "score": 0.8})
        if on(facing, t):
            faces.append({"width": 0.06, "frontal": True, "score": 0.9})
        samples.append({"t": t, "persons": persons, "faces": faces})
    base = speech_level if speech_level is not None else 0.1
    sp = [1.0 if on(speech, k * CO.WIN) else base for k in range(N)]
    work = [(0, D)] if work is None else work
    states, t = [], 0.0
    for a, b in sorted(work):
        if a > t:
            states.append({"state": "idle", "t_start": t, "t_end": a})
        states.append({"state": "work", "t_start": a, "t_end": b})
        t = b
    if t < D:
        states.append({"state": "idle", "t_start": t, "t_end": D})
    return {"samples": samples, "speech": sp}, {"duration_s": D, "states": states, "events": []}


def test_worker_passing_by_is_not_collaboration():
    s, tl = make(person=[(10, 11.5)], near=[(10.5, 11)])
    assert CO.detect(s, tl) == []


def test_worker_crossing_close_without_facing_is_not_collaboration():
    s, tl = make(near=[(20, 26)])
    assert CO.detect(s, tl) == []


def test_standing_silently_while_wearer_keeps_working_is_not_collaboration():
    s, tl = make(facing=[(10, 25)])  # someone faces the wearer, but work never pauses
    assert CO.detect(s, tl) == []


def test_talking_while_working_independently_is_not_collaboration():
    s, tl = make(person=[(5, 50)], speech=[(5, 50)])  # voices around, nobody facing, work continues
    assert CO.detect(s, tl) == []


def test_noisy_environment_without_people_is_not_collaboration():
    s, tl = make(speech=[(0, D)], work=[(0, 20), (40, D)])  # machine noise everywhere, wearer pauses alone
    assert CO.detect(s, tl) == []


def test_single_flicker_is_ignored():
    s, tl = make(facing=[(30, 30.5)], speech=[(30, 30.5)], work=[(0, 29), (31, D)])
    assert CO.detect(s, tl) == []


def test_real_collaboration_is_detected_with_high_confidence():
    # work pauses, a coworker comes close, faces the wearer, they talk, then work resumes
    s, tl = make(facing=[(20, 30)], speech=[(21, 29)], work=[(0, 20), (30, D)])
    ev = CO.detect(s, tl)
    assert len(ev) == 1
    e = ev[0]
    assert e["type"] == "collaboration" and e["confidence"] >= C.COLLAB_CONFIRMED
    assert 18 <= e["t_start"] <= 21 and 29 <= e["t_end"] <= 32
    assert e["evidence"]["work_resumes"] and "facing" in e["note"]
    assert "discuss" not in e["note"].lower()  # never claims what was said


def test_collaboration_without_speech_is_only_possible():
    s, tl = make(facing=[(20, 30)], work=[(0, 20), (30, D)])  # e.g. too noisy to hear
    ev = CO.detect(s, tl)
    assert len(ev) == 1 and ev[0]["type"] == "possible_collaboration"
    assert C.COLLAB_POSSIBLE <= ev[0]["confidence"] < C.COLLAB_CONFIRMED


def test_occluded_face_does_not_split_one_event():
    # the face drops out every third window (occlusion / 2 fps flicker)
    spans = [(20 + 1.5 * i, 20 + 1.5 * i + 1.0) for i in range(8)]
    s, tl = make(near=[(20, 32)], facing=spans, speech=[(20, 32)], work=[(0, 20), (32, D)])
    ev = CO.detect(s, tl)
    assert len(ev) == 1 and ev[0]["t_end"] - ev[0]["t_start"] >= 10


def test_speech_threshold_adapts_to_noisy_clips():
    # background "speech" level 0.8 everywhere: VAD can't be trusted, so speech must not count
    s, tl = make(facing=[(20, 30)], speech=[(20, 30)], work=[(0, 20), (30, D)], speech_level=0.8)
    sig = CO.signals(s, tl)
    assert sig["speech"].max() == 0


def test_apply_writes_events_into_timeline(tmp_path, monkeypatch):
    s, tl = make(facing=[(20, 30)], speech=[(21, 29)], work=[(0, 20), (30, D)])
    tl["clip_id"] = "zz-collab"
    d = tmp_path / "zz-collab"
    d.mkdir()
    (d / "timeline.json").write_text(json.dumps(tl))
    (d / "social.json").write_text(json.dumps(s))
    monkeypatch.setattr(CO, "OUT", tmp_path)
    CO.apply("zz-collab")
    CO.apply("zz-collab")  # idempotent
    out = json.loads((d / "timeline.json").read_text())
    collab = [e for e in out["events"] if e["type"] in CO.TYPES]
    assert len(collab) == 1 and collab[0]["severity"] == "blue" and collab[0]["evidence"]
