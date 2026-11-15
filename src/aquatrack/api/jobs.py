"""Analysis jobs: request, run, record.

States on the video document: uploaded -> queued -> analyzing -> ready | failed.
`failed` can be queued again up to MAX_ATTEMPTS; `ready` only with an explicit rerun.

Jobs run on one worker thread inside the API process. That is enough for local development
and it keeps uploads from blocking web requests, but it is NOT a durable job queue: a job
that is queued or running when the process stops is lost. Such a job is treated as stale
after STALE_AFTER_S and may be requested again. Production needs a real queue and worker.
"""

import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aquatrack.analysis.pipeline import analyze
from aquatrack.analysis.pose.sources import PoseSource, PoseSourceError
from aquatrack.analysis.video import video_identity
from aquatrack.api.store import Store, VideoRecord
from aquatrack.contracts import AnalysisJobStatus as Status
from aquatrack.contracts import JobError

log = logging.getLogger("aquatrack.jobs")

# How many times one video may be analysed before it has to be uploaded again. Development
# with precomputed pose files often needs more tries (a video fails until its pose file has
# been added), so the limit can be raised with AQUATRACK_MAX_ATTEMPTS.
MAX_ATTEMPTS = int(os.environ.get("AQUATRACK_MAX_ATTEMPTS", "3"))
STALE_AFTER_S = 600
MAX_VIDEO_BYTES = 500 * 1024 * 1024  # same limit as storage.rules


class JobRequestError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class JobRequest:
    status: str
    started: bool  # True when this request queued a new run
    attempts: int


def _now() -> datetime:
    return datetime.now(UTC)


def _age_seconds(value: Any, now: datetime) -> float:
    """Seconds since a stored timestamp; a missing one counts as very old."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return float("inf")
    if not isinstance(value, datetime):
        return float("inf")
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return (now - value).total_seconds()


def request_analysis(
    store: Store, video_id: str, uid: str, rerun: bool = False, now: datetime | None = None
) -> JobRequest:
    """Queue analysis for the caller's own video. Safe to call twice: a second request
    while one is queued or running returns that job instead of starting another."""
    now = now or _now()

    def decide(video: VideoRecord | None):
        # Someone else's video looks exactly like a missing one.
        if video is None or video.uid != uid:
            raise JobRequestError(404, "Video not found.")
        if not video.storage_path.startswith(f"videos/{uid}/"):
            raise JobRequestError(422, "This upload record is not valid.")
        if video.content_type and not video.content_type.startswith("video/"):
            raise JobRequestError(422, "This upload is not a video.")
        if video.size_bytes > MAX_VIDEO_BYTES:
            raise JobRequestError(422, "This video is too large to analyse.")

        attempts = int(video.job.get("attempts", 0) or 0)
        status = video.status
        if status in (Status.QUEUED, Status.ANALYZING):
            marker = video.job.get("startedAt") or video.job.get("queuedAt")
            if _age_seconds(marker, now) < STALE_AFTER_S:
                return None, JobRequest(status=status, started=False, attempts=attempts)
            status = Status.FAILED  # lost when the server stopped; allow another go
        if status == Status.READY and not rerun:
            return None, JobRequest(status=status, started=False, attempts=attempts)
        if status == Status.READY:
            attempts = 0
        if status == Status.FAILED and attempts >= MAX_ATTEMPTS:
            raise JobRequestError(
                409, "This video has already been tried the maximum number of times."
            )
        attempts += 1
        job = {
            "attempts": attempts,
            "queuedAt": now,
            "startedAt": None,
            "finishedAt": None,
            "poseSource": None,
            "errorCode": None,
            "errorMessage": None,
            "retryable": None,
        }
        updates = {"status": Status.QUEUED.value, "job": job}
        return updates, JobRequest(status=Status.QUEUED.value, started=True, attempts=attempts)

    return store.transact(video_id, decide)


def _fail(store: Store, video: VideoRecord, error: JobError) -> None:
    attempts = int(video.job.get("attempts", 1) or 1)
    store.update_video(
        video.id,
        {
            "status": Status.FAILED.value,
            "job": {
                **video.job,
                "finishedAt": _now(),
                "errorCode": error.code,
                "errorMessage": error.message,
                "retryable": bool(error.retryable and attempts < MAX_ATTEMPTS),
            },
        },
    )
    log.warning("analysis failed video=%s code=%s attempt=%s", video.id, error.code, attempts)


def run_job(store: Store, source: PoseSource, video_id: str) -> None:
    """Run one queued job to `ready` or `failed`. Never raises: every failure is recorded
    on the video with a reason the swimmer can read (no file paths, no internals)."""
    video = store.get_video(video_id)
    if video is None or video.status != Status.QUEUED:
        return
    video.job = {**video.job, "startedAt": _now(), "poseSource": source.name}
    store.update_video(video_id, {"status": Status.ANALYZING.value, "job": video.job})
    try:
        with tempfile.TemporaryDirectory(prefix="aquatrack-job-") as tmp:
            work = Path(tmp)
            local = work / f"video{Path(video.storage_path).suffix}"
            try:
                store.download_video(video.storage_path, local)
            except Exception:
                log.exception("download failed video=%s", video_id)
                return _fail(
                    store,
                    video,
                    JobError(
                        code="video_unavailable",
                        message="The uploaded video could not be loaded.",
                        retryable=True,
                    ),
                )
            try:
                identity = video_identity(local)
            except ValueError:
                return _fail(
                    store,
                    video,
                    JobError(
                        code="video_unreadable",
                        message="This file could not be read as a video.",
                        retryable=False,
                    ),
                )
            try:
                raw = source.get_raw_pose(local, identity, video_id)
            except PoseSourceError as e:
                return _fail(
                    store, video, JobError(code=e.code, message=e.message, retryable=e.retryable)
                )
            result, processed = analyze(raw, video_id, video.session, identity)

            raw_path = raw.save(work / "raw_pose.npz")
            processed_path = processed.save(work / "processed_pose.npz")
            attempts = int(video.job.get("attempts", 1) or 1)
            analysis_id = f"{_now():%Y%m%dT%H%M%S}-{attempts:02d}"
            store.save_analysis(
                video,
                analysis_id,
                result.to_firestore(),
                {"raw_pose.npz": raw_path, "processed_pose.npz": processed_path},
            )
        rate = next((m.value for m in result.measurements if m.key == "stroke_rate"), None)
        store.update_video(
            video_id,
            {
                "status": Status.READY.value,
                "job": {**video.job, "finishedAt": _now()},
                "latestAnalysisId": analysis_id,
                "analysisSummary": {
                    "schemaVersion": result.schema_version,
                    "grade": result.quality.grade.value,
                    "validPosePct": result.quality.valid_pose_pct,
                    "strokeMeasurable": result.stroke.measurable,
                    "cyclesPerMin": rate,  # the same number the result page shows
                    "strokeCount": result.stroke.stroke_count,
                },
            },
        )
        log.info("analysis ready video=%s grade=%s", video_id, result.quality.grade.value)
    except Exception:
        log.exception("analysis crashed video=%s", video_id)
        _fail(
            store,
            video,
            JobError(
                code="internal_error",
                message="Something went wrong while analysing this video.",
                retryable=True,
            ),
        )


class JobRunner:
    """One background thread, jobs in request order. See the module note on durability."""

    def __init__(self, store: Store, source: PoseSource):
        self.store = store
        self.source = source
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aquatrack-job")

    def submit(self, video_id: str) -> None:
        self._pool.submit(run_job, self.store, self.source, video_id)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


class InlineRunner:
    """Runs the job before `submit` returns. For tests."""

    def __init__(self, store: Store, source: PoseSource):
        self.store = store
        self.source = source

    def submit(self, video_id: str) -> None:
        run_job(self.store, self.source, video_id)
