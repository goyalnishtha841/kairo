"""Motion Skill Profiler: kinematic features, label-free clustering, recording-not-person wording."""
import numpy as np
import pytest

import copilot
import skill_profile as S
from conftest import processed_clips

CLIPS = processed_clips()
FS = 15.0


def bell(n=20, peaks=1):
    """Speed profile of a reach with `peaks` sub-movements (each a smooth bell)."""
    return np.concatenate([np.sin(np.pi * np.linspace(0, 1, n)) ** 2 for _ in range(peaks)]) * 0.4


# ---------------------------------------------------------------- kinematics on synthetic signals
def test_sparc_rates_a_single_bell_smoother_than_a_corrected_reach():
    assert S.sparc(bell(30), FS) > S.sparc(bell(15, peaks=3), FS)
    assert S.sparc(bell(30), FS) < 0


def test_peaks_counts_sub_movements_and_ignores_ripple():
    assert len(S._peaks(bell(20))) == 1
    assert len(S._peaks(bell(20, peaks=3))) == 3
    ripple = bell(30) + 0.003 * np.sin(np.linspace(0, 40, 30))
    assert len(S._peaks(ripple)) == 1


def _track(grip, pos):
    n = len(grip)
    return {"t": np.arange(n) / FS, "grip": np.array(grip, float), "pos": np.array(pos, float)}


def test_regrasp_is_a_close_at_the_same_spot_soon_after_release():
    grip = [0.8, 0.2, 0.2, 0.8, 0.8, 0.2, 0.2]          # close, release, close again
    assert len(S._regrasps(_track(grip, [[0.5, 0.3]] * 7))) == 1
    far = [[0.5, 0.3]] * 4 + [[0.8, 0.3]] * 3            # second close somewhere else: a new grasp
    assert S._regrasps(_track(grip, far)) == []
    slow = [0.8, 0.2, 0.8] + [0.8] * 40 + [0.2]          # second close after > 2 s
    assert S._regrasps(_track(slow, [[0.5, 0.3]] * len(slow))) == []


def test_head_motion_is_removed_from_hand_velocity():
    """A hand that stays put in the scene while the head pans moves in the image but not in the world."""
    n, pan = 30, 0.2
    frames = []
    for i in range(n):
        x = 0.3 + pan * i / FS                              # scene (and hand) drift right in the image
        lm = [[x, 0.5, 0.0]] * 21
        frames.append({"t": i / FS, "cam": {"pan": pan, "tilt": 0.0, "ok": True},
                       "hands": [{"id": "L", "lm": lm}]})
    tr = S._tracks({"frames": frames})["L"]
    assert np.nanmax(np.linalg.norm(tr["vel"][2:-2], axis=1)) < 1e-6


def test_kmeans_separates_obvious_groups_deterministically():
    X = np.array([[0.0], [0.1], [0.2], [5.0], [5.1], [5.2]])
    lab, _, _ = S.kmeans(X, 2)
    assert len(set(lab[:3])) == 1 and len(set(lab[3:])) == 1 and lab[0] != lab[3]
    assert S.silhouette(X, lab) > 0.9
    assert (S.kmeans(X, 2)[0] == lab).all()


# ---------------------------------------------------------------- on the processed recordings
needs_data = pytest.mark.skipif(len(CLIPS) < 6, reason="needs several processed clips")


@pytest.fixture(scope="module")
def cache():
    return {}


@needs_data
def test_every_recording_gets_a_pattern_and_explanation(cache):
    for c in CLIPS:
        p = S.profile(c, cache)
        assert p["pattern"] in S.PATTERNS[3]
        assert 0 <= p["expertise_index"] <= 100 and 0 <= p["confidence"] <= 1
        assert p["summary"].startswith(f"This recording shows {p['pattern'].lower()}")
        assert set(p["fingerprint"]) == {f["label"] for f in p["features"]}
        assert "not a person" in p["note"]


@needs_data
def test_patterns_follow_the_expertise_axis(cache):
    """Labels must agree with the evidence: every expert-like recording outranks every beginner-like one."""
    prof = [S.profile(c, cache) for c in CLIPS]
    rank = {name: i for i, name in enumerate(S.PATTERNS[3])}
    for a in prof:
        for b in prof:
            if rank[a["pattern"]] < rank[b["pattern"]]:
                assert a["expertise_index"] >= b["expertise_index"]


@needs_data
def test_beginner_features_cite_timestamps(cache):
    for c in CLIPS:
        for f in S.profile(c, cache)["features"]:
            if f["tone"] == "beginner" and f["evidence"]:
                assert all(e.startswith(f"[{c}@") for e in f["evidence"])
                return
    pytest.skip("no beginner-tone feature with evidence")


@needs_data
def test_cluster_map_covers_every_recording(cache):
    pts = S.cluster_map(cache)
    assert {p["clip_id"] for p in pts} == set(CLIPS)


@needs_data
def test_skill_api_and_copilot(client):
    r = client.get(f"/api/skill?clip={CLIPS[0]}").json()
    assert r["clip_id"] == CLIPS[0] and r["clusters"] and r["features"]
    assert client.get("/api/skill?clip=nope").status_code == 404
    ans = copilot.ask("Which recordings show expert or beginner motion?", CLIPS, engine="rules")
    assert "Motion skill patterns" in ans["answer"] and "not a person" in ans["answer"]
