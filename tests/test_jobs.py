from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from conftest import make_raw_pose

from aquatrack.analysis.pose.rtmw_backend import select_target
from aquatrack.analysis.pose.sources import PrecomputedPoseSource
from aquatrack.analysis.video import video_identity
from aquatrack.api import jobs
from aquatrack.api.jobs import InlineRunner, JobRequestError, request_analysis, run_job
from aquatrack.api.store import MemoryStore
from aquatrack.contracts import AnalysisResult, ProcessedPose, RawPose, Selection

UID, OTHER = "swimmer-1", "swimmer-2"
PATH = f"videos/{UID}/vid1.mp4"


@pytest.fixture
def store(swim_video):
    s = MemoryStore()
    s.files[PATH] = swim_video.read_bytes()
    s.videos["vid1"] = {
        "uid": UID,
        "storagePath": PATH,
        "status": "uploaded",
        "contentType": "video/mp4",
        "sizeBytes": len(s.files[PATH]),
        "stroke": "Freestyle",
        "camera": "Underwater",
        "distance": "50 m",
        "poolLength": "25 m",
    }
    return s


@pytest.fixture
def source(tmp_path, swim_video):
    src = PrecomputedPoseSource(tmp_path / "poses")
    src.directory.mkdir()
    make_raw_pose(swim_video).save(src.path_for(video_identity(swim_video).sha256))
    return src


def test_request_queues_then_run_reaches_ready_with_real_results(store, source):
    job = request_analysis(store, "vid1", UID)
    assert (job.status, job.started, job.attempts) == ("queued", True, 1)
    assert store.videos["vid1"]["status"] == "queued"
    run_job(store, source, "vid1")
    video = store.videos["vid1"]
    assert video["status"] == "ready" and video["job"]["poseSource"] == "precomputed"
    assert video["job"]["errorCode"] is None and video["job"]["finishedAt"] is not None
    summary = video["analysisSummary"]
    assert summary == {
        "schemaVersion": "1.2",
        "grade": "good",
        "validPosePct": 100.0,
        "strokeMeasurable": True,
        "cyclesPerMin": 50.0,
        "strokeCount": None,  # the two-arm total of schema 1.0 is no longer produced
        "cycleCount": 8,
        "metricsReliable": summary["metricsReliable"],
        "metricsLimited": summary["metricsLimited"],
    }
    assert summary["metricsReliable"] >= 5
    doc = store.analyses[("vid1", video["latestAnalysisId"])]
    assert doc["uid"] == UID
    result = AnalysisResult.model_validate({k: v for k, v in doc.items() if k != "uid"})
    assert result.session.stroke == "Freestyle" and result.video.frame_count == 250
    assert result.config.detector_weights == "yolo11m.pt"
    # per-frame arrays go to storage, not into the document
    kinds = {a.kind: a for a in result.artifacts}
    assert set(kinds) == {"raw_pose", "processed_pose"}
    assert kinds["raw_pose"].storage_path.startswith(f"analysis/{UID}/vid1/")
    assert "keypoints" not in doc and len(str(doc)) < 50_000


def test_saved_artifacts_are_readable_and_separate(store, source, tmp_path):
    InlineRunner(store, source).submit("vid1") if request_analysis(store, "vid1", UID) else None
    paths = [p for p in store.files if p.startswith("analysis/")]
    raw_path = next(p for p in paths if p.endswith("raw_pose.npz"))
    processed_path = next(p for p in paths if p.endswith("processed_pose.npz"))
    (tmp_path / "r.npz").write_bytes(store.files[raw_path])
    (tmp_path / "p.npz").write_bytes(store.files[processed_path])
    assert len(RawPose.load(tmp_path / "r.npz")) == len(ProcessedPose.load(tmp_path / "p.npz"))


def test_duplicate_request_does_not_start_a_second_job(store):
    first = request_analysis(store, "vid1", UID)
    second = request_analysis(store, "vid1", UID)
    assert first.started and not second.started
    assert second.status == "queued" and second.attempts == 1


def test_request_for_a_ready_video_returns_it_unless_rerun(store, source):
    request_analysis(store, "vid1", UID)
    run_job(store, source, "vid1")
    again = request_analysis(store, "vid1", UID)
    assert (again.status, again.started) == ("ready", False)
    rerun = request_analysis(store, "vid1", UID, rerun=True)
    assert (rerun.status, rerun.started, rerun.attempts) == ("queued", True, 1)


def test_missing_pose_data_fails_with_a_reason_and_no_results(store, tmp_path):
    request_analysis(store, "vid1", UID)
    run_job(store, PrecomputedPoseSource(tmp_path / "none"), "vid1")
    video = store.videos["vid1"]
    assert video["status"] == "failed"
    assert video["job"]["errorCode"] == "pose_data_missing" and video["job"]["retryable"]
    assert "pose data" in video["job"]["errorMessage"].lower()
    assert "analysisSummary" not in video and not store.analyses


def test_retry_after_failure_then_limit(store, source, tmp_path):
    empty = PrecomputedPoseSource(tmp_path / "none")
    for attempt in (1, 2, 3):
        job = request_analysis(store, "vid1", UID)
        assert job.started and job.attempts == attempt
        run_job(store, empty, "vid1")
        assert store.videos["vid1"]["status"] == "failed"
    assert store.videos["vid1"]["job"]["retryable"] is False  # last allowed attempt
    with pytest.raises(JobRequestError) as e:
        request_analysis(store, "vid1", UID)
    assert e.value.status_code == 409


def test_retry_limit_can_be_raised_for_development(store, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "MAX_ATTEMPTS", 5)
    empty = PrecomputedPoseSource(tmp_path / "none")
    for attempt in range(1, 5):
        assert request_analysis(store, "vid1", UID).attempts == attempt
        run_job(store, empty, "vid1")
        assert store.videos["vid1"]["job"]["retryable"] is True


def test_retry_succeeds_once_pose_data_exists(store, source, tmp_path):
    request_analysis(store, "vid1", UID)
    run_job(store, PrecomputedPoseSource(tmp_path / "none"), "vid1")
    job = request_analysis(store, "vid1", UID)
    assert job.attempts == 2
    run_job(store, source, "vid1")
    video = store.videos["vid1"]
    assert video["status"] == "ready" and video["job"]["errorCode"] is None


def test_another_users_video_looks_missing(store):
    for video_id, uid in (("vid1", OTHER), ("nope", UID)):
        with pytest.raises(JobRequestError) as e:
            request_analysis(store, video_id, uid)
        assert e.value.status_code == 404
    assert store.videos["vid1"]["status"] == "uploaded"


@pytest.mark.parametrize(
    "change",
    [
        {"storagePath": f"videos/{OTHER}/vid1.mp4"},
        {"contentType": "application/pdf"},
        {"sizeBytes": 600 * 1024 * 1024},
    ],
)
def test_invalid_upload_records_are_refused(store, change):
    store.videos["vid1"].update(change)
    with pytest.raises(JobRequestError) as e:
        request_analysis(store, "vid1", UID)
    assert e.value.status_code == 422


def test_stale_job_can_be_requested_again(store):
    start = datetime(2026, 11, 1, tzinfo=UTC)
    request_analysis(store, "vid1", UID, now=start)
    soon = request_analysis(store, "vid1", UID, now=start + timedelta(seconds=30))
    assert not soon.started
    later = request_analysis(
        store, "vid1", UID, now=start + timedelta(seconds=jobs.STALE_AFTER_S + 1)
    )
    assert later.started and later.attempts == 2


def test_unreadable_video_fails_without_retry(store, source):
    store.files[PATH] = b"this is not a video"
    request_analysis(store, "vid1", UID)
    run_job(store, source, "vid1")
    job = store.videos["vid1"]["job"]
    assert (job["errorCode"], job["retryable"]) == ("video_unreadable", False)


def test_pose_for_a_different_video_fails_the_job(store, tmp_path, swim_video):
    src = PrecomputedPoseSource(tmp_path)
    wrong = make_raw_pose(swim_video)
    wrong.meta.video.frame_count = 999
    wrong.save(src.path_for(video_identity(swim_video).sha256))
    request_analysis(store, "vid1", UID)
    run_job(store, src, "vid1")
    assert store.videos["vid1"]["job"]["errorCode"] == "pose_video_mismatch"
    assert not store.analyses


def test_unexpected_crash_is_recorded_without_internals(store, source, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("/secret/path/model.onnx exploded")

    monkeypatch.setattr(jobs, "analyze", boom)
    request_analysis(store, "vid1", UID)
    run_job(store, source, "vid1")
    job = store.videos["vid1"]["job"]
    assert store.videos["vid1"]["status"] == "failed" and job["errorCode"] == "internal_error"
    assert "secret" not in job["errorMessage"] and "/" not in job["errorMessage"]


def test_run_job_ignores_videos_that_are_not_queued(store, source):
    run_job(store, source, "vid1")
    assert store.videos["vid1"]["status"] == "uploaded"


# ---------- target selection ----------

SWIMMER = [100.0, 100.0, 300.0, 160.0, 0.6]
REFLECTION = [80.0, 20.0, 330.0, 90.0, 0.5]  # bigger box, on the surface above the swimmer


def test_tracking_keeps_the_swimmer_when_a_bigger_box_appears():
    both = np.array([REFLECTION, SWIMMER])
    previous = np.array(SWIMMER[:4]) + 4
    picked, how = select_target(both, previous)
    assert picked.tolist() == SWIMMER and how is Selection.OVERLAP
    largest, how = select_target(both, previous, mode="largest")
    assert largest.tolist() == REFLECTION and how is Selection.LARGEST


def test_tracking_starts_from_area_times_confidence_and_falls_back_to_nearest():
    both = np.array([REFLECTION, SWIMMER])
    first, how = select_target(both, None)
    assert how is Selection.FIRST and first.tolist() == REFLECTION
    far = np.array([[900.0, 500.0, 1000.0, 560.0, 0.9], [400.0, 110.0, 600.0, 170.0, 0.3]])
    picked, how = select_target(far, np.array(SWIMMER[:4]))
    assert how is Selection.NEAREST and picked[0] == 400.0
    assert select_target(np.empty((0, 5)), None) == (None, Selection.NONE)


# ---------- interpretation: stored next to the analysis, never overwriting ----------


def test_analysis_is_followed_by_an_interpretation_stored_as_its_own_document(store, source):
    request_analysis(store, "vid1", UID)
    run_job(store, source, "vid1")
    video = store.videos["vid1"]
    ((key, doc),) = store.interpretations.items()
    assert key == ("vid1", video["latestInterpretationId"])
    assert doc["uid"] == UID and doc["analysis_id"] == video["latestAnalysisId"]
    assert doc["interpretation_version"] == "1.0" and doc["baseline"] is True
    assert video["interpretationSummary"]["observations"] == len(doc["observations"]) > 0
    assert video["interpretationSummary"]["priorities"] == 0
    # The analysis document itself is unchanged by interpretation.
    analysis = store.analyses[("vid1", video["latestAnalysisId"])]
    assert "observations" not in analysis and analysis["schema_version"] == "1.2"


def test_reinterpreting_adds_a_document_and_needs_no_video_or_pose(store, source):
    request_analysis(store, "vid1", UID)
    run_job(store, source, "vid1")
    first_id = store.videos["vid1"]["latestInterpretationId"]
    first = dict(store.interpretations[("vid1", first_id)])
    store.files.clear()  # no video, no pose arrays: only the stored result is read

    found = jobs.reinterpret(store, "vid1", UID)

    assert len(store.interpretations) == 2
    assert store.interpretations[("vid1", first_id)] == first  # earlier one untouched
    assert store.videos["vid1"]["latestInterpretationId"] != first_id
    assert found.analysis_id == store.videos["vid1"]["latestAnalysisId"]
    with pytest.raises(JobRequestError) as other:
        jobs.reinterpret(store, "vid1", OTHER)
    assert other.value.status_code == 404
    assert len(store.interpretations) == 2


def test_only_finished_videos_can_be_interpreted(store):
    with pytest.raises(JobRequestError) as e:
        jobs.reinterpret(store, "vid1", UID)
    assert e.value.status_code == 409 and store.interpretations == {}


def test_history_is_the_swimmers_own_earlier_swims_and_their_profile(store, source):
    request_analysis(store, "vid1", UID)
    run_job(store, source, "vid1")
    done = store.videos["vid1"]
    analysis = store.analyses[("vid1", done["latestAnalysisId"])]
    done["createdAt"] = "2026-11-10T10:00:00+00:00"
    # An earlier swim of the same swimmer, a later one, and someone else's.
    for vid, uid, created in (
        ("earlier", UID, "2026-11-01T10:00:00+00:00"),
        ("later", UID, "2026-11-12T10:00:00+00:00"),
        ("theirs", OTHER, "2026-11-01T10:00:00+00:00"),
    ):
        store.videos[vid] = {**done, "uid": uid, "createdAt": created, "latestAnalysisId": "a"}
        store.analyses[(vid, "a")] = {**analysis, "uid": uid}
    store.profiles[UID] = {"swim_level": "hobby", "pbs": [{"event": "50 Free", "seconds": 40.0}]}
    store.profiles[OTHER] = {"swim_level": "competitive", "goals": ["steadier_rhythm"]}

    found = jobs.reinterpret(store, "vid1", UID)

    assert [s.video_id for s in found.sessions] == ["earlier"]  # not later, not someone else's
    assert found.sessions[0].compatible and not found.baseline
    assert found.context.swim_level == "hobby" and found.context.personal_best_s == 40.0
    assert found.context.goals == []  # the other swimmer's goals are not this swimmer's
    assert any(f.category == "history" for f in found.observations)


def test_a_failed_interpretation_does_not_undo_the_analysis(store, source, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("interpretation bug")

    monkeypatch.setattr(jobs, "interpret", boom)
    request_analysis(store, "vid1", UID)
    run_job(store, source, "vid1")
    assert store.videos["vid1"]["status"] == "ready" and store.interpretations == {}
    assert store.videos["vid1"].get("latestInterpretationId") is None


# ---------- feedback: built from the interpretation, stored without overwriting ----------


def test_feedback_is_stored_after_interpretation_and_reused_for_the_same_inputs(store, source):
    request_analysis(store, "vid1", UID)
    run_job(store, source, "vid1")
    video = store.videos["vid1"]
    ((key, doc),) = store.feedback.items()
    assert key == ("vid1", video["latestFeedbackId"]) and doc["uid"] == UID
    assert doc["interpretation_id"] == video["latestInterpretationId"]
    assert doc["feedback_version"] == "1.0" and doc["explanation"]["source"] == "template"
    assert video["feedbackSummary"]["priorities"] == 0 and video["feedbackSummary"]["goals"] == []
    assert not any(i["category"] in ("focus", "priority", "education") for i in doc["items"])


def test_changing_goals_gives_new_feedback_and_keeps_the_old(store, source):
    request_analysis(store, "vid1", UID)
    run_job(store, source, "vid1")
    first_id = store.videos["vid1"]["latestFeedbackId"]
    first = dict(store.feedback[("vid1", first_id)])
    store.profiles[UID] = {
        "swim_level": "hobby",
        "goals": ["breathing", "not_a_goal"],
        "primary_goal": "breathing",
        "weak_note": "my kick",
    }

    jobs.reinterpret(store, "vid1", UID)

    second_id = store.videos["vid1"]["latestFeedbackId"]
    assert second_id != first_id and store.feedback[("vid1", first_id)] == first
    second = store.feedback[("vid1", second_id)]
    assert second["goals_used"] == ["breathing"] and second["primary_goal"] == "breathing"
    education = [i for i in second["items"] if i["category"] == "education"]
    assert len(education) == 1 and education[0]["personal"] is False
    assert not any(i["category"] in ("focus", "priority") for i in second["items"])
    assert "my kick" not in str(second)  # the swimmer's own note is never analysed or copied

    # Interpreting again with nothing changed adds an interpretation run but no new feedback.
    count = len(store.feedback)
    jobs.reinterpret(store, "vid1", UID)
    assert len(store.feedback) == count and store.videos["vid1"]["latestFeedbackId"] == second_id


def test_a_mocked_model_rewording_is_stored_only_when_it_passes_validation(store, source):
    class Liar:
        model = "mock"

        def explain(self, payload):
            item = payload["items"][0]
            return {
                "items": [
                    {
                        "id": item["id"],
                        "text": "Your stroke rate was 99 per minute.",
                        "citations": [],
                    }
                ]
            }

    request_analysis(store, "vid1", UID)
    run_job(store, source, "vid1")
    video = store.get_video("vid1")
    jobs.interpret_video(store, video, video.latest_analysis_id, explainer=Liar())
    doc = store.feedback[("vid1", store.videos["vid1"]["latestFeedbackId"])]
    assert doc["explanation"]["source"] == "template" and "rejected" in doc["explanation"]["note"]
    assert all(i["explained"] == "" for i in doc["items"])
