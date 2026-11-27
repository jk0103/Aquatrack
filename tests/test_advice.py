"""Hybrid advice: the motion profile, the model request, the checks and the fallback.

No model is called here: `FakeInterpreter` returns prepared answers and `FakeClient` records
the request the OpenAI adapter would send. The swimmers are synthetic. Passing these tests
shows the plumbing and the checks work; it says nothing about how accurate the advice is on
real swimmers.
"""

import copy
import hashlib
import json

import numpy as np
import pytest
import synthetic
from conftest import make_raw_pose
from fastapi.testclient import TestClient
from firebase_admin import auth

from aquatrack.analysis import advice, motion_profile
from aquatrack.analysis.metrics.cycles import analyze_strokes
from aquatrack.analysis.pipeline import analyze
from aquatrack.analysis.processing import process
from aquatrack.api import firebase, jobs, main
from aquatrack.api.jobs import InlineRunner
from aquatrack.api.store import MemoryStore, artifact_path
from aquatrack.contracts import Advice, SessionInfo, VideoIdentity

PERIOD = 1.2


def swimmer(name="steady", frames=360, **kw):
    t = synthetic.times(frames)
    if name == "alternating":
        bent = synthetic.swimmer_xy(t, PERIOD, elbow_deg=95.0)
        straight = synthetic.swimmer_xy(t, PERIOD, elbow_deg=160.0)
        odd = (np.floor(t / PERIOD).astype(int) % 2).astype(bool)
        xy = bent.copy()
        xy[odd] = straight[odd]
    else:
        xy = synthetic.swimmer_xy(t, PERIOD, elbow_deg=120.0, **kw)
    identity = VideoIdentity(
        sha256=hashlib.sha256(name.encode()).hexdigest(),
        frame_count=frames,
        fps=float(synthetic.FPS),
        width=synthetic.W,
        height=synthetic.H,
    )
    raw = make_raw_pose(xy=xy, video=identity)
    if name == "arm_missing":
        for start in range(30, frames, 90):
            raw.keypoints[start : start + 55, [7, 8, 9, 10], 2] = 0.4
    return raw


def analysed(raw, video_id="vid1"):
    result, _ = analyze(raw, video_id, SessionInfo(stroke="Freestyle", camera="Underwater"))
    clean = process(raw).clean
    return result, motion_profile.build(clean, analyze_strokes(clean), result)


@pytest.fixture(scope="module")
def steady():
    return analysed(swimmer())


@pytest.fixture(scope="module")
def alternating():
    return analysed(swimmer("alternating"))


def suggestion(**over):
    base = {
        "title": "Elbow bend changes from stroke to stroke",
        "category": "arm_path",
        "noticed": "The elbow angle at mid-pull alternates between strokes.",
        "why_it_may_matter": "A pull that changes shape may make the stroke harder to repeat.",
        "try_this": "Aim to feel the same pressure on the forearm at the start of each pull.",
        "drill_id": "tech.catch_up",
        "drill_note": "Swim it easily and notice the start of each pull.",
        "check_next_time": "Compare the elbow at mid-pull on successive strokes.",
        "confidence": "medium",
        "cycles_supporting": 4,
        "evidence_refs": ["motion.cycle_to_cycle.elbow_angle_at_mid_pull_deg"],
        "times_s": [1.0, 2.2],
    }
    return base | over


def answer(**over):
    base = {
        "data_quality": [{"problem": "One side-on camera only.", "affects": "depth"}],
        "observations": [
            {
                "statement": "Cycle time stayed the same.",
                "evidence_refs": ["cycle_duration"],
                "times_s": [],
            }
        ],
        "consistent": [
            {
                "statement": "The rhythm repeats from cycle to cycle.",
                "evidence_refs": ["rhythm_variation"],
                "times_s": [],
            }
        ],
        "suggestions": [suggestion()],
        "summary": "A steady rhythm with a pull that changes shape.",
    }
    return base | over


class FakeInterpreter:
    model, reasoning = "fake-model", "high"

    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls, self.payloads = reply, error, 0, []

    def interpret(self, payload):
        self.calls += 1
        self.payloads.append(payload)
        if self.error:
            raise self.error
        return copy.deepcopy(self.reply), {
            "input_tokens": 10,
            "output_tokens": 5,
            "reasoning_tokens": 2,
        }


# ---------- the motion profile ----------


def test_the_profile_describes_each_cycle_the_same_way_and_agrees_with_the_result(steady):
    result, profile = steady
    motion = profile["motion"]
    arm = motion["arm_followed"]
    assert 1 <= len(motion["cycles"]) <= motion_profile.MAX_CYCLES
    assert all(len(c["samples"]) == motion_profile.SAMPLES for c in motion["cycles"])
    assert set(motion["cycle_to_cycle"]) == set(motion_profile.FEATURES)
    stored = [c.duration_s for c in result.stroke.cycles if c.arm == arm]
    assert [c["duration_s"] for c in motion["cycles"]] == [
        round(d, 2) for d in stored[: len(motion["cycles"])]
    ]
    for c in motion["cycles"]:  # boundaries and duration come from the same event
        assert c["end_s"] - c["start_s"] == pytest.approx(c["duration_s"], abs=0.05)
    assert {m["key"]: m["value"] for m in profile["metrics"]} == {
        m.key: m.value for m in result.metrics
    }
    json.dumps(profile)  # plain data
    assert len(json.dumps(profile)) < 80_000  # a summary, not a dump of keypoints


def test_the_profile_is_the_same_for_the_same_pose():
    raw = swimmer()
    assert motion_profile.digest(analysed(raw)[1]) == motion_profile.digest(analysed(raw)[1])


def test_the_profile_shows_a_change_between_cycles_and_a_steady_shoulder(alternating):
    series = alternating[1]["motion"]["cycle_to_cycle"]
    elbow = series["elbow_angle_at_mid_pull_deg"]
    assert elbow["max"] - elbow["min"] > 40 and elbow["share_of_direction_reversals"] == 1.0
    duration = series["cycle_duration_s"]
    assert duration["max"] - duration["min"] < 0.05


def test_the_profile_says_what_the_tracker_could_not_see():
    _, profile = analysed(swimmer("arm_missing"))
    wrist = profile["motion"]["tracking_of_followed_side"]["wrist"]
    assert wrist["usable_share"] < 0.6 and wrist["unusable_stretches_s"]
    assert not any(c.get("trusted") for c in profile["stroke_cycles"]["cycles"])


# ---------- the request ----------


class FakeClient:
    def __init__(self):
        self.requests = []
        self.responses = self

    def create(self, **kwargs):
        self.requests.append(kwargs)

        class Usage:
            input_tokens, output_tokens = 100, 50
            output_tokens_details = type("D", (), {"reasoning_tokens": 20})()

        return type(
            "R",
            (),
            {
                "status": "completed",
                "output_text": json.dumps(answer()),
                "usage": Usage(),
                "incomplete_details": None,
            },
        )()


def test_the_request_asks_the_chosen_model_for_a_strict_answer_and_sends_only_the_profile(steady):
    client = FakeClient()
    interpreter = advice.OpenAIInterpreter(client=client)
    result, profile = steady
    made = advice.build_advice(
        result, "a1", profile, interpreter, goals=["stroke_consistency"], level="hobby"
    )
    request = client.requests[0]
    assert len(client.requests) == 1
    assert request["model"] == "gpt-6.2-astra" and request["reasoning"] == {"effort": "high"}
    assert request["store"] is False
    assert (
        request["text"]["format"]["strict"] is True
        and request["text"]["format"]["schema"] == advice.SCHEMA
    )
    sent = json.loads(request["input"])
    assert set(sent) == {"swimmer_goals", "swimmer_level", "drills_you_may_choose", "data"}
    assert sent["data"] == profile and sent["drills_you_may_choose"]
    assert isinstance(request["input"], str)  # text only: no image parts
    assert "input_image" not in json.dumps(request) and "@" not in request["input"]  # no e-mail
    assert "measurements, not video" in request["instructions"]
    assert made.source == "ai" and made.model == "gpt-6.2-astra" and made.reasoning_effort == "high"
    assert made.usage == {"input_tokens": 100, "output_tokens": 50, "reasoning_tokens": 20}


# ---------- what is kept, what is dropped ----------


def test_a_checked_answer_becomes_advice_with_its_provenance(alternating):
    result, profile = alternating
    made = advice.build_advice(result, "a1", profile, FakeInterpreter(answer()))
    assert made.source == "ai" and made.fallback_reason == ""
    assert made.profile_sha256 == motion_profile.digest(profile)
    assert (
        made.prompt_version == advice.PROMPT_VERSION
        and made.analysis_schema_version == result.schema_version
    )
    s = made.suggestions[0]
    assert (s.drill_id, s.drill_name) == ("tech.catch_up", "Catch-up freestyle")
    assert s.evidence_refs and s.cycles_supporting == 4
    assert [o.statement for o in made.consistent] == ["The rhythm repeats from cycle to cycle."]
    assert made.general_practice and made.limitations and not made.rejected


@pytest.mark.parametrize(
    "change,why",
    [
        (
            {"noticed": "The elbow angle was 123.45 degrees on every stroke."},
            "not in the measurements",
        ),
        ({"try_this": "Hold a tempo of 4321.5 s per stroke."}, "not in the measurements"),
        ({"evidence_refs": ["pull_depth"]}, "was not measured"),
        ({"evidence_refs": ["made_up_metric"]}, "not in the data"),
        ({"evidence_refs": []}, "names no measurement"),
        ({"times_s": [999.0]}, "outside the clip"),
        ({"cycles_supporting": 1}, "fewer than two stroke cycles"),
        ({"cycles_supporting": 400}, "more stroke cycles than were measured"),
        ({"drill_note": "Do it while holding your breath."}, "breath-holding"),
        ({"try_this": "Your elbow should be at the ideal angle."}, "ideal angle"),
        ({"why_it_may_matter": "This will make you faster."}, "promises"),
    ],
)
def test_a_suggestion_that_fails_a_check_is_dropped_and_the_others_are_kept(
    alternating, change, why
):
    result, profile = alternating
    statuses = {m["key"]: m["status"] for m in profile["metrics"]}
    assert statuses["pull_depth"] == "unavailable" and statuses["cycle_duration"] != "unavailable"
    good = suggestion(title="Good one", category="timing", evidence_refs=["cycle_duration"])
    reply = answer(suggestions=[suggestion(**change), good])
    made = advice.build_advice(result, "a1", profile, FakeInterpreter(reply))
    assert made.source == "ai"
    assert [s.title for s in made.suggestions] == ["Good one"]
    assert len(made.rejected) == 1 and why in " ".join(made.rejected[0].reasons)


def test_a_suggestion_about_joints_that_were_mostly_unusable_is_dropped(alternating):
    _, profile = alternating
    profile = copy.deepcopy(profile)
    profile["motion"]["tracking_of_followed_side"]["wrist"]["usable_share"] = 0.3
    kept = advice.check(answer(), profile)
    assert not kept["suggestions"] and "wrist" in " ".join(kept["rejected"][0].reasons)


def test_an_unknown_drill_is_removed_without_dropping_the_suggestion(alternating):
    result, profile = alternating
    made = advice.build_advice(
        result, "a1", profile, FakeInterpreter(answer(suggestions=[suggestion(drill_id="made.up")]))
    )
    assert (
        len(made.suggestions) == 1
        and made.suggestions[0].drill_id == ""
        and made.suggestions[0].drill_name == ""
    )


def test_at_most_three_suggestions_and_a_steady_stroke_is_not_a_problem(steady):
    result, profile = steady
    four = [
        suggestion(title=f"S{n}", category="timing", evidence_refs=["cycle_duration"])
        for n in range(4)
    ]
    made = advice.build_advice(result, "a1", profile, FakeInterpreter(answer(suggestions=four)))
    assert [s.title for s in made.suggestions] == ["S0", "S1", "S2"]
    none = advice.build_advice(result, "a1", profile, FakeInterpreter(answer(suggestions=[])))
    assert (
        none.source == "ai" and none.suggestions == [] and none.consistent and none.general_practice
    )


def test_an_observation_with_an_invented_number_is_dropped(steady):
    result, profile = steady
    reply = answer(
        observations=[
            {
                "statement": "Stroke rate was 987.6 per minute.",
                "evidence_refs": ["stroke_rate"],
                "times_s": [],
            },
            {
                "statement": "Cycle time stayed the same.",
                "evidence_refs": ["cycle_duration"],
                "times_s": [],
            },
        ]
    )
    made = advice.build_advice(result, "a1", profile, FakeInterpreter(reply))
    assert [o.statement for o in made.observations] == ["Cycle time stayed the same."]
    assert made.rejected[0].kind == "observation"


# ---------- falling back ----------


def test_without_a_model_or_when_it_fails_the_advice_is_deterministic(steady):
    result, profile = steady
    off = advice.build_advice(result, "a1", profile, None, goals=["stroke_consistency"])
    assert off.source == "deterministic" and "not enabled" in off.fallback_reason
    assert off.suggestions == [] and 1 <= len(off.general_practice) <= 3
    failed = advice.build_advice(
        result, "a1", profile, FakeInterpreter(error=advice.AdviceError("timed out"))
    )
    assert failed.source == "deterministic" and "failed" in failed.fallback_reason
    broken = advice.build_advice(result, "a1", profile, FakeInterpreter({"nonsense": True}))
    assert broken.source == "deterministic"
    bad = answer(observations=[], consistent=[], suggestions=[suggestion(cycles_supporting=0)])
    nothing = advice.build_advice(result, "a1", profile, FakeInterpreter(bad))
    assert (
        nothing.source == "deterministic"
        and nothing.rejected
        and "passed the checks" in nothing.fallback_reason
    )


def test_nothing_measurable_means_no_call_at_all():
    result, profile = analysed(swimmer("arm_missing"))
    fake = FakeInterpreter(answer())
    made = advice.build_advice(result, "a1", profile, fake)
    assert fake.calls == 0 and made.source == "deterministic" and made.general_practice


def test_general_practice_comes_from_the_library_and_names_no_problem():
    for goals in (["stroke_consistency"], []):
        items = advice.general_practice(goals, "beginner")
        assert 1 <= len(items) <= 3
        assert all("not based on a problem" in i.reason for i in items)


def test_older_and_minimal_advice_documents_still_load():
    doc = {
        "video_id": "v",
        "analysis_id": "a",
        "source": "deterministic",
        "uid": "u",
        "future_field": 1,
    }
    assert Advice.model_validate(doc).suggestions == []


# ---------- stored once, read without a call ----------


@pytest.fixture
def stored(alternating):
    result, _ = alternating
    store = MemoryStore()
    store.videos["vid1"] = {
        "uid": "u1",
        "storagePath": "videos/u1/vid1.mp4",
        "status": "ready",
        "latestAnalysisId": "a1",
    }
    store.analyses[("vid1", "a1")] = {**result.to_firestore(), "uid": "u1"}
    raw = swimmer("alternating")
    return store, raw, result


def test_the_same_analysis_is_interpreted_once_and_regenerated_only_on_request(stored):
    store, raw, result = stored
    fake = FakeInterpreter(answer())
    first = jobs.advise_video(store, store.get_video("vid1"), "a1", raw, result, fake)
    again = jobs.advise_video(store, store.get_video("vid1"), "a1", raw, result, fake)
    assert fake.calls == 1 and first["id"] == again["id"]
    assert store.get_video("vid1").latest_advice_id == first["id"]
    assert store.videos["vid1"]["adviceSummary"]["source"] == "ai"
    # reading it back needs no model
    assert Advice.model_validate(store.get_advice("vid1", first["id"])).suggestions
    new = jobs.advise_video(
        store, store.get_video("vid1"), "a1", raw, result, fake, regenerate=True
    )
    assert fake.calls == 2 and new["id"] != first["id"]
    assert store.get_advice("vid1", first["id"]) is not None  # the earlier one is untouched
    assert len(store.advice) == 2


def test_a_different_model_or_no_model_gets_its_own_document(stored):
    store, raw, result = stored
    ai = jobs.advise_video(
        store, store.get_video("vid1"), "a1", raw, result, FakeInterpreter(answer())
    )
    plain = jobs.advise_video(store, store.get_video("vid1"), "a1", raw, result, None)
    assert ai["id"] != plain["id"] and plain["source"] == "deterministic"


def test_only_the_owner_can_ask_for_advice_again(stored, monkeypatch, tmp_path):
    store, raw, _ = stored
    path = tmp_path / "raw.npz"
    raw.save(path)
    store.files[artifact_path(store.get_video("vid1"), "a1", "raw_pose.npz")] = path.read_bytes()

    def fake_verify(token):
        if token in ("owner", "other"):
            return {"uid": "u1" if token == "owner" else "u2"}
        raise auth.InvalidIdTokenError("bad")

    monkeypatch.setattr(firebase, "verify_token", fake_verify)
    monkeypatch.delenv("AQUATRACK_ADVICE_PROVIDER", raising=False)
    main.app.dependency_overrides[main.get_runner] = lambda: InlineRunner(store, None)
    try:
        client = TestClient(main.app)
        assert client.post("/videos/vid1/advice").status_code == 401
        assert (
            client.post(
                "/videos/vid1/advice", headers={"Authorization": "Bearer other"}
            ).status_code
            == 404
        )
        res = client.post("/videos/vid1/advice", headers={"Authorization": "Bearer owner"})
        assert res.status_code == 201 and res.json()["source"] == "deterministic"
    finally:
        main.app.dependency_overrides.clear()


# ---------- inside the job: advice never costs the analysis, and never holds the lease ----------


@pytest.fixture
def queued(swim_video):
    store = MemoryStore()
    path = "videos/u1/vid1.mp4"
    store.files[path] = swim_video.read_bytes()
    store.videos["vid1"] = {
        "uid": "u1",
        "storagePath": path,
        "status": "uploaded",
        "contentType": "video/mp4",
        "sizeBytes": len(store.files[path]),
        "stroke": "Freestyle",
        "camera": "Underwater",
    }
    jobs.request_analysis(store, "vid1", "u1")

    class Source:
        name = "fake"

        def get_raw_pose(self, video_path, video, video_id):
            return make_raw_pose(swim_video)  # FAKE pose source: a synthetic swimmer, no model

    return store, Source()


def test_a_failing_advice_step_leaves_the_analysis_and_feedback_saved(queued, monkeypatch):
    store, source = queued
    monkeypatch.setattr(
        advice,
        "interpreter_from_env",
        lambda: FakeInterpreter(error=advice.AdviceError("timed out")),
    )
    jobs.run_job(store, source, "vid1", "w1")
    video = store.get_video("vid1")
    assert video.status == "ready" and video.latest_analysis_id and video.latest_feedback_id
    stored = store.get_advice("vid1", video.latest_advice_id)
    assert stored["source"] == "deterministic" and "failed" in stored["fallback_reason"]
    assert stored["general_practice"]


def test_a_crash_in_the_advice_step_still_leaves_a_finished_analysis(queued, monkeypatch):
    store, source = queued

    def boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(motion_profile, "build", boom)
    jobs.run_job(store, source, "vid1", "w1")
    video = store.get_video("vid1")
    assert video.status == "ready" and video.latest_analysis_id and video.latest_feedback_id
    assert video.latest_advice_id == "" and not store.advice
    assert store.videos["vid1"]["job"].get("errorCode") is None


def test_the_model_is_called_after_the_job_is_finished_so_a_slow_answer_cannot_time_it_out(
    queued, monkeypatch
):
    """The analysis is stored and the job closed before the advice call starts: no lease is
    held while the model thinks, so its 40 to 80 seconds cannot expire a lease or the job."""
    store, source = queued
    seen = {}

    class Slow(FakeInterpreter):
        def interpret(self, payload):
            v = store.videos["vid1"]
            seen.update(
                status=v["status"],
                lease=v["job"].get("leaseExpiresAt"),
                owner=v["job"].get("leaseOwner"),
                analysis=v.get("latestAnalysisId"),
            )
            return super().interpret(payload)

    slow = Slow(answer(suggestions=[]))
    monkeypatch.setattr(advice, "interpreter_from_env", lambda: slow)
    jobs.run_job(store, source, "vid1", "w1")
    assert slow.calls == 1
    assert seen["status"] == "ready" and seen["analysis"]
    assert not seen["lease"] and not seen["owner"]
    assert jobs.claim_next(store, "w2") is None  # nothing left for another worker to take over


def test_a_short_clip_gives_tentative_suggestions_not_none(alternating):
    result, profile = alternating
    short = copy.deepcopy(profile)
    for n, cycle in enumerate(short["motion"]["cycles"]):
        cycle["trusted"] = n < 3  # only three trusted cycles of the followed arm
    made = advice.build_advice(result, "a1", short, FakeInterpreter(answer()))
    s = made.suggestions[0]
    assert made.trusted_cycles == 3 and s.tentative
    assert "only 3 stroke cycles" in s.tentative_reasons[0]
    full = advice.build_advice(result, "a1", profile, FakeInterpreter(answer()))
    assert full.trusted_cycles >= 4 and not full.suggestions[0].tentative


def test_a_timing_suggestion_within_a_few_frames_is_tentative(steady):
    result, profile = steady
    p = copy.deepcopy(profile)
    series = p["motion"]["cycle_to_cycle"]["front_phase_s"]
    series["min"], series["max"] = 0.20, 0.28  # two frames apart at 25 fps
    timing = suggestion(category="timing", evidence_refs=["motion.cycle_to_cycle.front_phase_s"])
    made = advice.build_advice(result, "a1", p, FakeInterpreter(answer(suggestions=[timing])))
    s = made.suggestions[0]
    assert s.tentative and "video frames" in " ".join(s.tentative_reasons)
    series["max"] = 0.60  # a clear difference is not marked for this reason
    clear = advice.build_advice(result, "a1", p, FakeInterpreter(answer(suggestions=[timing])))
    assert not clear.suggestions[0].tentative
