"""The durable analysis queue and the worker: claiming, leases, recovery after a crash,
cancellation, timeouts, limits on the uploaded file, and what happens around deletion.

Orchestration is tested with FAKE inference adapters (`FakeInference`, `ExplodingInference`):
they return a synthetic swimmer's pose and say nothing about the real models. One test at
the end runs a real public clip with pose data that the real models produced earlier
(a development fixture, skipped when those local files are absent). Neither kind of test is
model inference on a new video: that has not been run through this worker."""
# ruff: noqa: E501

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from conftest import make_raw_pose

from aquatrack.analysis.pose.sources import PoseSourceError, PrecomputedPoseSource
from aquatrack.analysis.video import video_identity
from aquatrack.api import jobs
from aquatrack.api.jobs import (
    JobRequestError,
    Worker,
    cancel_analysis,
    claim,
    claim_next,
    heartbeat,
    request_analysis,
    run_job,
)
from aquatrack.api.store import MemoryStore

UID, OTHER = "swimmer-1", "swimmer-2"
T0 = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


class FakeInference:
    """FAKE pose source for orchestration tests: a synthetic swimmer, no model."""

    name = "fake"

    def __init__(self, swim_video, hook=None):
        self.video, self.hook, self.calls = swim_video, hook, 0

    def get_raw_pose(self, video_path, video, video_id):
        self.calls += 1
        if self.hook:
            self.hook(self.calls)
        return make_raw_pose(self.video)


def add_video(store, swim_video, vid="vid1", uid=UID, **over):
    path = f"videos/{uid}/{vid}.mp4"
    store.files[path] = swim_video.read_bytes()
    store.videos[vid] = {
        "uid": uid,
        "storagePath": path,
        "status": "uploaded",
        "contentType": "video/mp4",
        "sizeBytes": len(store.files[path]),
        "stroke": "Freestyle",
        "camera": "Underwater",
    } | over


@pytest.fixture
def store(swim_video):
    s = MemoryStore()
    add_video(s, swim_video)
    return s


@pytest.fixture
def fake(swim_video):
    return FakeInference(swim_video)


def job(store, vid="vid1"):
    return store.videos[vid]["job"]


def status(store, vid="vid1"):
    return store.videos[vid]["status"]


# ---------- the queue is durable and a job is claimed once ----------


def test_a_queued_job_survives_a_restart_and_is_picked_up_by_a_new_worker(store, fake):
    request_analysis(store, "vid1", UID)
    assert status(store) == "queued" and job(store)["analysisId"]
    # "restart": nothing in memory is kept; a brand-new worker reads the stored queue
    assert Worker(store, fake, "after-restart").run_once() is True
    assert status(store) == "ready" and job(store)["leaseOwner"] is None
    assert Worker(store, fake, "after-restart").run_once() is False  # nothing left to do


def test_only_one_of_many_workers_claiming_at_once_gets_the_job(store):
    request_analysis(store, "vid1", UID)
    winners, barrier = [], threading.Barrier(8)

    def go(n):
        barrier.wait()
        if claim(store, "vid1", f"w{n}") is not None:
            winners.append(n)

    threads = [threading.Thread(target=go, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(winners) == 1 and job(store)["leaseOwner"] == f"w{winners[0]}"
    assert status(store) == "analyzing"


def test_jobs_are_taken_oldest_first_and_never_someone_elses_twice(store, swim_video):
    add_video(store, swim_video, "vid2", uid=OTHER)
    request_analysis(store, "vid2", OTHER, now=T0)
    request_analysis(store, "vid1", UID, now=T0 + timedelta(minutes=1))
    first = claim_next(store, "w1", now=T0 + timedelta(minutes=2))
    second = claim_next(store, "w2", now=T0 + timedelta(minutes=2))
    assert (first.id, second.id) == ("vid2", "vid1")
    assert claim_next(store, "w3", now=T0 + timedelta(minutes=2)) is None


# ---------- leases, crashes and recovery ----------


def test_a_dead_workers_job_is_recovered_when_its_lease_runs_out(store, fake):
    request_analysis(store, "vid1", UID, now=T0)
    assert claim(store, "vid1", "dies", now=T0) is not None  # ... and the worker is killed
    soon = T0 + timedelta(seconds=jobs.LEASE_S - 1)
    assert claim(store, "vid1", "other", now=soon) is None  # the lease still protects it
    later = T0 + timedelta(seconds=jobs.LEASE_S + 1)
    again = claim(store, "vid1", "other", now=later)
    assert again is not None and again.job["leaseOwner"] == "other"
    assert again.job["interruptions"] == 1 and again.job["attempts"] == 1
    jobs.process(store, fake, again, "other")
    assert status(store) == "ready"


def test_a_job_that_keeps_killing_its_worker_is_failed_not_retried_for_ever(store):
    request_analysis(store, "vid1", UID, now=T0)
    now = T0
    for _ in range(jobs.MAX_INTERRUPTIONS + 1):
        assert claim(store, "vid1", "dies", now=now) is not None
        now += timedelta(seconds=jobs.LEASE_S + 1)
    assert claim(store, "vid1", "dies", now=now) is None
    assert status(store) == "failed" and job(store)["errorCode"] == "worker_interrupted"
    assert job(store)["retryable"] is True and "interrupted" in job(store)["errorMessage"]
    assert request_analysis(store, "vid1", UID).started  # the swimmer may try again


def test_a_worker_that_lost_its_lease_stores_nothing_and_cannot_finish_the_job(store, swim_video):
    """Worker A stalls past its lease; worker B takes over and finishes. When A wakes up it
    must not write a result or change the job."""
    request_analysis(store, "vid1", UID)
    state = {}

    def a_stalls_and_b_takes_over(call):
        expired = datetime.now(UTC) + timedelta(seconds=jobs.LEASE_S + 5)
        taken = claim(store, "vid1", "B", now=expired)
        jobs.process(store, FakeInference(swim_video), taken, "B")
        state["after_b"] = (status(store), dict(store.analyses), job(store)["finishedAt"])

    run_job(store, FakeInference(swim_video, a_stalls_and_b_takes_over), "vid1", "A")
    assert state["after_b"][0] == "ready"
    assert (status(store), dict(store.analyses), job(store)["finishedAt"]) == state["after_b"]
    assert job(store)["errorCode"] is None


def test_running_the_same_job_twice_writes_the_same_analysis_not_two(store, fake):
    request_analysis(store, "vid1", UID, now=T0)
    first = claim(store, "vid1", "A", now=T0)
    jobs.process(store, fake, first, "A")  # A finishes ...
    analysis_id = store.videos["vid1"]["latestAnalysisId"]
    assert analysis_id == job(store)["analysisId"] == f"{T0:%Y%m%dT%H%M%S}-01"
    store.videos["vid1"]["status"] = "analyzing"  # ... but its "done" was lost; lease expired
    store.videos["vid1"]["job"]["leaseExpiresAt"] = datetime(2020, 1, 1, tzinfo=UTC)
    Worker(store, fake, "B").run_once()
    assert status(store) == "ready" and list(store.analyses) == [("vid1", analysis_id)]
    assert len([f for f in store.files if f.startswith("analysis/")]) == 2  # raw + processed, once


def test_heartbeats_renew_the_lease_and_report_progress(store):
    request_analysis(store, "vid1", UID, now=T0)
    claim(store, "vid1", "A", now=T0)
    heartbeat(store, "vid1", "A", "pose", now=T0 + timedelta(seconds=60))
    assert job(store)["leaseExpiresAt"] == T0 + timedelta(seconds=60 + jobs.LEASE_S)
    assert job(store)["progress"]["stage"] == "pose"
    with pytest.raises(jobs.LeaseLost):
        heartbeat(store, "vid1", "someone-else", now=T0 + timedelta(seconds=61))
    with pytest.raises(jobs.TimedOut):
        heartbeat(store, "vid1", "A", now=T0 + timedelta(seconds=jobs.JOB_TIMEOUT_S + 1))


def test_a_run_that_takes_too_long_is_stopped_and_can_be_tried_again(
    store, swim_video, monkeypatch
):
    request_analysis(store, "vid1", UID)

    def very_slow(call):
        store.videos["vid1"]["job"]["startedAt"] = datetime.now(UTC) - timedelta(
            seconds=jobs.JOB_TIMEOUT_S + 10
        )

    run_job(store, FakeInference(swim_video, very_slow), "vid1")
    assert status(store) == "failed" and job(store)["errorCode"] == "timeout"
    assert job(store)["retryable"] is True and not store.analyses


def test_a_failure_while_saving_leaves_no_half_result_and_the_retry_succeeds(
    store, fake, monkeypatch
):
    request_analysis(store, "vid1", UID)
    real = store.save_analysis
    monkeypatch.setattr(store, "save_analysis", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    run_job(store, fake, "vid1")
    assert status(store) == "failed" and job(store)["errorCode"] == "internal_error"
    assert "disk" not in str(job(store)) and "latestAnalysisId" not in store.videos["vid1"]
    monkeypatch.setattr(store, "save_analysis", real)
    request_analysis(store, "vid1", UID)
    run_job(store, fake, "vid1")
    assert status(store) == "ready" and len(store.analyses) == 1


def test_an_inference_error_is_recorded_in_words_the_swimmer_can_read(store, swim_video):
    class ExplodingInference:
        """FAKE: a pose source that fails the way a real one reports failure."""

        name = "fake"

        def get_raw_pose(self, *a):
            raise PoseSourceError(
                "inference_failed", "The analysis could not be run.", retryable=True
            )

    request_analysis(store, "vid1", UID)
    run_job(store, ExplodingInference(), "vid1")
    assert (status(store), job(store)["errorCode"]) == ("failed", "inference_failed")
    assert job(store)["errorMessage"] == "The analysis could not be run."


# ---------- cancellation ----------


def test_a_queued_job_is_cancelled_at_once_and_costs_no_attempt(store, fake):
    request_analysis(store, "vid1", UID)
    assert cancel_analysis(store, "vid1", UID) == {"id": "vid1", "status": "canceled"}
    assert job(store)["attempts"] == 0 and job(store)["finishedAt"] is not None
    assert Worker(store, fake).run_once() is False  # a cancelled job is never run
    assert request_analysis(store, "vid1", UID).started and job(store)["attempts"] == 1


def test_a_running_job_stops_at_its_next_checkpoint_and_stores_nothing(store, swim_video):
    request_analysis(store, "vid1", UID)
    seen = {}

    def swimmer_cancels(call):
        seen["answer"] = cancel_analysis(store, "vid1", UID)

    run_job(store, FakeInference(swim_video, swimmer_cancels), "vid1")
    assert seen["answer"]["status"] == "analyzing"  # flagged; the worker is still busy
    assert status(store) == "canceled" and not store.analyses
    assert not [f for f in store.files if f.startswith("analysis/")]
    assert job(store)["leaseOwner"] is None and job(store)["attempts"] == 0


def test_cancelling_a_job_whose_worker_is_gone_does_not_wait_for_it(store):
    request_analysis(store, "vid1", UID, now=T0)
    claim(store, "vid1", "dead", now=T0)
    later = T0 + timedelta(seconds=jobs.LEASE_S + 1)
    assert cancel_analysis(store, "vid1", UID, now=later)["status"] == "canceled"


def test_only_the_owner_can_cancel_and_only_something_that_is_running(store):
    with pytest.raises(JobRequestError) as e:
        cancel_analysis(store, "vid1", UID)
    assert e.value.status_code == 409
    request_analysis(store, "vid1", UID)
    with pytest.raises(JobRequestError) as e:
        cancel_analysis(store, "vid1", OTHER)
    assert e.value.status_code == 404 and e.value.detail == "Video not found."
    assert status(store) == "queued"


# ---------- deletion and limits ----------


def test_deleting_a_video_stops_its_running_job_from_storing_anything(store, swim_video):
    request_analysis(store, "vid1", UID)

    def swimmer_deletes(call):
        jobs.delete_video(store, "vid1", UID)

    run_job(store, FakeInference(swim_video, swimmer_deletes), "vid1")
    assert "vid1" not in store.videos and not store.analyses
    assert not [f for f in store.files if "vid1" in f]


def test_a_video_being_deleted_is_never_claimed(store, fake):
    request_analysis(store, "vid1", UID)
    store.videos["vid1"]["status"] = "deleting"
    assert Worker(store, fake).run_once() is False


def test_one_swimmer_cannot_fill_the_queue(store, swim_video):
    for n in range(jobs.MAX_ACTIVE_JOBS + 1):
        add_video(store, swim_video, f"extra{n}")
    for n in range(jobs.MAX_ACTIVE_JOBS):
        request_analysis(store, f"extra{n}", UID)
    with pytest.raises(JobRequestError) as e:
        request_analysis(store, f"extra{jobs.MAX_ACTIVE_JOBS}", UID)
    assert e.value.status_code == 429 and "already have videos being analysed" in e.value.detail
    add_video(store, swim_video, "theirs", uid=OTHER)
    assert request_analysis(store, "theirs", OTHER).started  # someone else is not affected


@pytest.mark.parametrize(
    "limit,value,code",
    [
        ("MAX_VIDEO_SECONDS", 5.0, "video_too_long"),
        ("MAX_VIDEO_FRAMES", 100, "video_too_long"),
        ("MIN_VIDEO_SECONDS", 60.0, "video_too_short"),
        ("MAX_VIDEO_SIDE_PX", 100, "video_resolution"),
        ("MAX_VIDEO_BYTES", 1000, "video_too_large"),
    ],
)
def test_limits_are_checked_on_the_file_itself_not_on_what_the_upload_claims(
    store, fake, monkeypatch, limit, value, code
):
    store.videos["vid1"]["sizeBytes"] = 1  # the browser's claim; not trusted
    request_analysis(store, "vid1", UID)
    monkeypatch.setattr(jobs, limit, value)
    run_job(store, fake, "vid1")
    assert (status(store), job(store)["errorCode"]) == ("failed", code)
    assert job(store)["retryable"] is False and fake.calls == 0  # refused before any inference
    assert "/" not in job(store)["errorMessage"]


def test_a_file_that_is_not_a_video_is_refused_whatever_its_content_type_says(store, fake):
    store.files[f"videos/{UID}/vid1.mp4"] = b"#!/bin/sh\nrm -rf /\n" * 50
    store.videos["vid1"]["contentType"] = "video/mp4"
    request_analysis(store, "vid1", UID)
    run_job(store, fake, "vid1")
    assert (status(store), job(store)["errorCode"]) == ("failed", "video_unreadable")
    assert fake.calls == 0


def test_the_worker_loop_keeps_going_after_a_queue_error_and_stops_when_told(
    store, fake, monkeypatch
):
    worker = Worker(store, fake, "loop")
    calls = {"n": 0}
    real = store.list_pending_videos

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("firestore unreachable")
        if calls["n"] >= 4:
            worker.stop()
        return real()

    monkeypatch.setattr(store, "list_pending_videos", flaky)
    request_analysis(store, "vid1", UID)
    thread = threading.Thread(target=worker.run_forever, args=(0.01,))
    thread.start()
    thread.join(timeout=20)
    assert not thread.is_alive() and status(store) == "ready"


# ---------- regression with pose data the real models produced ----------

CLIP = Path("test_videos/public/front_crawl_underwater.webm")
POSES = Path("data/precomputed_pose")


@pytest.mark.skipif(
    not (CLIP.exists() and POSES.exists()),
    reason="local public clip or its saved pose data is absent",
)
def test_worker_runs_a_real_public_clip_from_saved_model_output_end_to_end():
    """DEVELOPMENT FIXTURE. The pose data was produced earlier by the real YOLO11m + RTMW-x
    models in Colab; here the worker only looks it up by the video's hash. This checks the
    worker, the limits and the pipeline on real numbers. It is not inference on a new video."""
    store = MemoryStore()
    path = f"videos/{UID}/real.webm"
    store.files[path] = CLIP.read_bytes()
    store.videos["real"] = {
        "uid": UID,
        "storagePath": path,
        "status": "uploaded",
        "contentType": "video/webm",
        "stroke": "Freestyle",
        "camera": "Underwater",
        "distance": "50 m",
    }
    assert PrecomputedPoseSource(POSES).path_for(video_identity(CLIP).sha256).exists()
    request_analysis(store, "real", UID)
    assert Worker(store, PrecomputedPoseSource(POSES), "regression").run_once()
    video = store.videos["real"]
    assert video["status"] == "ready" and video["job"]["poseSource"] == "precomputed"
    assert video["analysisSummary"]["grade"] == "good"
    assert video["analysisSummary"]["cyclesPerMin"] == pytest.approx(23.9, abs=0.2)
    assert video["sha256"] == video_identity(CLIP).sha256
    assert video["latestInterpretationId"] and video["latestFeedbackId"]
