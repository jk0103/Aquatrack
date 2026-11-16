"""Analysis jobs: request, claim, run, record.

States on the video document:
  uploaded -> queued -> analyzing -> ready | failed | canceled
`failed` and `canceled` can be queued again (up to MAX_ATTEMPTS failures); `ready` only with
an explicit rerun.

The queue is the video documents themselves. A request writes `status: queued` in a
transaction, so the job exists durably before anything runs. A worker (a thread inside the
API in development, or `python -m aquatrack.worker` as its own process) claims a job in a
transaction that gives it a lease, renews the lease while it works, and may only store
results while it still holds the lease. If a worker dies, its lease runs out and another
worker (or the same one after a restart) claims the job again; after MAX_INTERRUPTIONS such
recoveries the job fails with a readable reason instead of looping. The analysis id is fixed
when the job is queued, so a job that runs twice writes the same documents twice.

This is a Firestore-leased queue: enough for one or a few workers and no extra
infrastructure. It polls, so it is not meant for high volume. See docs/ANALYSIS_JOBS.md.
"""

import logging
import os
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aquatrack.analysis import comparison
from aquatrack.analysis.comparison import Session
from aquatrack.analysis.explain import Explainer, explain_feedback, explainer_from_env
from aquatrack.analysis.feedback import build_feedback, feedback_id
from aquatrack.analysis.interpretation import PriorSession, SwimmerContext, interpret
from aquatrack.analysis.pipeline import analyze
from aquatrack.analysis.pose.sources import PoseSource, PoseSourceError
from aquatrack.analysis.video import read_video_info, video_identity
from aquatrack.api.store import Store, VideoRecord
from aquatrack.contracts import AnalysisJobStatus as Status
from aquatrack.contracts import AnalysisResult, Interpretation, JobError

log = logging.getLogger("aquatrack.jobs")

# How many times one video may be analysed before it has to be uploaded again. Development
# with precomputed pose files often needs more tries (a video fails until its pose file has
# been added), so the limit can be raised with AQUATRACK_MAX_ATTEMPTS.
MAX_ATTEMPTS = int(os.environ.get("AQUATRACK_MAX_ATTEMPTS", "3"))
STALE_AFTER_S = 600
MAX_VIDEO_BYTES = 500 * 1024 * 1024  # same limit as storage.rules
# A worker must renew its lease within this time or the job may be claimed again.
LEASE_S = int(os.environ.get("AQUATRACK_JOB_LEASE_S", "120"))
# The longest one run may take before it is stopped and recorded as timed out.
JOB_TIMEOUT_S = int(os.environ.get("AQUATRACK_JOB_TIMEOUT_S", "3600"))
# How many times a job may be recovered from a dead worker before it is failed.
MAX_INTERRUPTIONS = 2
# Jobs one swimmer may have queued or running at once.
MAX_ACTIVE_JOBS = int(os.environ.get("AQUATRACK_MAX_ACTIVE_JOBS", "2"))
# Limits checked on the file itself, never on what the upload record claims.
MAX_VIDEO_SECONDS = float(os.environ.get("AQUATRACK_MAX_VIDEO_SECONDS", "180"))
MIN_VIDEO_SECONDS = 2.0
MAX_VIDEO_FRAMES = int(os.environ.get("AQUATRACK_MAX_VIDEO_FRAMES", "9000"))
MAX_VIDEO_SIDE_PX = 4096


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


def _lease_expired(job: dict, now: datetime) -> bool:
    return _age_seconds(job.get("leaseExpiresAt"), now) >= 0  # missing counts as expired


def request_analysis(
    store: Store, video_id: str, uid: str, rerun: bool = False, now: datetime | None = None
) -> JobRequest:
    """Queue analysis for the caller's own video. Safe to call twice: a second request
    while one is queued or running returns that job instead of starting another."""
    now = now or _now()
    active = sum(
        v.id != video_id and v.status in (Status.QUEUED, Status.ANALYZING)
        for v in store.list_videos(uid)
    )

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
        if status == Status.DELETING:
            raise JobRequestError(409, "This video is being deleted.")
        if status in (Status.QUEUED, Status.ANALYZING):
            # A queued job waits for a worker and a running one is protected by its lease;
            # both are recovered by the queue itself. Asking again only starts over when
            # the job is old AND nobody holds a lease on it (no worker is running at all).
            marker = video.job.get("startedAt") or video.job.get("queuedAt")
            if _age_seconds(marker, now) < STALE_AFTER_S or not _lease_expired(video.job, now):
                return None, JobRequest(status=status, started=False, attempts=attempts)
            status = Status.FAILED
        if status == Status.READY and not rerun:
            return None, JobRequest(status=status, started=False, attempts=attempts)
        if status == Status.READY:
            attempts = 0
        if status == Status.FAILED and attempts >= MAX_ATTEMPTS:
            raise JobRequestError(
                409, "This video has already been tried the maximum number of times."
            )
        if active >= MAX_ACTIVE_JOBS:
            raise JobRequestError(
                429, "You already have videos being analysed. Wait for one to finish."
            )
        attempts += 1
        job = {
            "attempts": attempts,
            # Fixed now, so a job that is recovered and run again writes the same analysis.
            "analysisId": f"{now:%Y%m%dT%H%M%S}-{attempts:02d}",
            "leaseOwner": None,
            "leaseExpiresAt": None,
            "heartbeatAt": None,
            "interruptions": 0,
            "cancelRequested": False,
            "progress": None,
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


class LeaseLost(Exception):
    """Another worker owns the job now, or it is no longer running. Store nothing."""


class Cancelled(Exception):
    """The swimmer cancelled the job."""


class TimedOut(Exception):
    """The run went past JOB_TIMEOUT_S."""


def claim(
    store: Store, video_id: str, worker_id: str, now: datetime | None = None
) -> VideoRecord | None:
    """Take one job, atomically. Returns the claimed record, or None if it is not there to
    take (already running under a live lease, finished, cancelled, deleted). Two workers
    can never both get it: the claim is one transaction on the video document."""
    now = now or _now()

    def decide(video: VideoRecord | None):
        if video is None:
            return None, None
        job = dict(video.job)
        if video.status == Status.QUEUED:
            if job.get("cancelRequested"):
                return {"status": Status.CANCELED.value, "job": _closed(job, now)}, None
        elif video.status == Status.ANALYZING and _lease_expired(job, now):
            # The worker that had it stopped renewing: recover the job, a limited number
            # of times, so a video that kills its worker cannot loop for ever.
            job["interruptions"] = int(job.get("interruptions", 0) or 0) + 1
            if job.get("cancelRequested"):
                return {"status": Status.CANCELED.value, "job": _closed(job, now)}, None
            if job["interruptions"] > MAX_INTERRUPTIONS:
                attempts = int(job.get("attempts", 1) or 1)
                job = _closed(job, now) | {
                    "errorCode": "worker_interrupted",
                    "errorMessage": "The analysis was interrupted more than once.",
                    "retryable": attempts < MAX_ATTEMPTS,
                }
                return {"status": Status.FAILED.value, "job": job}, None
        else:
            return None, None
        job |= {
            "leaseOwner": worker_id,
            "leaseExpiresAt": now + timedelta(seconds=LEASE_S),
            "heartbeatAt": now,
            "startedAt": now,
            "progress": {"stage": "starting", "at": now},
        }
        return {"status": Status.ANALYZING.value, "job": job}, True

    if not store.transact(video_id, decide):
        return None
    return store.get_video(video_id)


def _closed(job: dict, now: datetime) -> dict:
    return job | {"finishedAt": now, "leaseOwner": None, "leaseExpiresAt": None}


def claim_next(store: Store, worker_id: str, now: datetime | None = None) -> VideoRecord | None:
    """The oldest job that can be taken, claimed. None when there is nothing to do."""
    now = now or _now()
    pending = sorted(
        store.list_pending_videos(), key=lambda v: _age_seconds(v.job.get("queuedAt"), now)
    )
    for video in reversed(pending):  # oldest first
        claimed = claim(store, video.id, worker_id, now)
        if claimed is not None:
            return claimed
    return None


def heartbeat(
    store: Store, video_id: str, worker_id: str, stage: str = "", now: datetime | None = None
) -> None:
    """Renew the lease and report progress. Raises if this worker must stop: the lease was
    lost, the swimmer cancelled, the run took too long, or the video is being deleted."""
    now = now or _now()

    def decide(video: VideoRecord | None):
        if (
            video is None
            or video.status != Status.ANALYZING
            or video.job.get("leaseOwner") != worker_id
        ):
            return None, "lost"
        if video.job.get("cancelRequested"):
            return None, "cancelled"
        if _age_seconds(video.job.get("startedAt"), now) > JOB_TIMEOUT_S:
            return None, "timeout"
        job = video.job | {
            "leaseExpiresAt": now + timedelta(seconds=LEASE_S),
            "heartbeatAt": now,
        }
        if stage:
            job["progress"] = {"stage": stage, "at": now}
        return {"job": job}, "ok"

    outcome = store.transact(video_id, decide)
    if outcome == "cancelled":
        raise Cancelled
    if outcome == "timeout":
        raise TimedOut
    if outcome != "ok":
        raise LeaseLost


def _finish(store: Store, video_id: str, worker_id: str, status: Status, fields: dict) -> bool:
    """Close the job, but only if this worker still holds it. A worker that lost its lease
    while it was busy can therefore never overwrite what the new owner is doing."""

    def decide(video: VideoRecord | None):
        if (
            video is None
            or video.status != Status.ANALYZING
            or video.job.get("leaseOwner") != worker_id
        ):
            return None, False
        job = _closed(video.job, _now()) | fields.get("job", {})
        rest = {k: v for k, v in fields.items() if k != "job"}
        return {"status": status.value, "job": job, **rest}, True

    return bool(store.transact(video_id, decide))


def _fail(store: Store, video: VideoRecord, worker_id: str, error: JobError) -> None:
    attempts = int(video.job.get("attempts", 1) or 1)
    job = {
        "errorCode": error.code,
        "errorMessage": error.message,
        "retryable": bool(error.retryable and attempts < MAX_ATTEMPTS),
    }
    if _finish(store, video.id, worker_id, Status.FAILED, {"job": job}):
        log.warning("analysis failed video=%s code=%s attempt=%s", video.id, error.code, attempts)


class _KeepAlive:
    """Renews the lease on a timer while a long step (pose inference) runs, and remembers
    why the worker has to stop. The step itself is not interrupted: the stop is acted on at
    the next checkpoint, and nothing is stored after a lost lease in any case."""

    def __init__(self, store: Store, video_id: str, worker_id: str, every_s: float | None):
        self.store, self.video_id, self.worker_id = store, video_id, worker_id
        self.every_s = every_s
        self.stop_reason: Exception | None = None
        self._done = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self):
        if self.every_s:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self._done.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self):
        while not self._done.wait(self.every_s):
            try:
                heartbeat(self.store, self.video_id, self.worker_id)
            except (LeaseLost, Cancelled, TimedOut) as e:
                self.stop_reason = e
                return
            except Exception:  # a failed renewal is retried; the lease has slack for it
                log.warning("heartbeat failed video=%s", self.video_id)

    def checkpoint(self, stage: str) -> None:
        if self.stop_reason is not None:
            raise self.stop_reason
        heartbeat(self.store, self.video_id, self.worker_id, stage)


def check_video_limits(path: Path) -> JobError | None:
    """Limits on the file as it really is. The upload record's size and type come from the
    browser and are not trusted for this."""
    if path.stat().st_size > MAX_VIDEO_BYTES:
        return JobError(
            retryable=False, code="video_too_large", message="This video is too large to analyse."
        )
    try:
        info = read_video_info(path)
    except Exception:
        return JobError(
            retryable=False,
            code="video_unreadable",
            message="This file could not be read as a video.",
        )
    if info.frame_count <= 0 or info.fps <= 0 or info.width <= 0 or info.height <= 0:
        return JobError(
            retryable=False,
            code="video_unreadable",
            message="This file could not be read as a video.",
        )
    if max(info.width, info.height) > MAX_VIDEO_SIDE_PX:
        return JobError(
            retryable=False,
            code="video_resolution",
            message="This video's resolution is too high to analyse.",
        )
    if info.duration_s > MAX_VIDEO_SECONDS or info.frame_count > MAX_VIDEO_FRAMES:
        return JobError(
            retryable=False,
            code="video_too_long",
            message=(
                f"This video is too long. Upload a clip of up to {MAX_VIDEO_SECONDS:.0f} seconds."
            ),
        )
    if info.duration_s < MIN_VIDEO_SECONDS:
        return JobError(
            retryable=False,
            code="video_too_short",
            message="This video is too short to analyse. Film at least a few stroke cycles.",
        )
    return None


def run_job(
    store: Store,
    source: PoseSource,
    video_id: str,
    worker_id: str = "inline",
    keep_alive_s: float | None = None,
) -> None:
    """Claim one job and run it to `ready`, `failed` or `canceled`. Never raises: every
    failure is recorded on the video with a reason the swimmer can read (no file paths, no
    internals). Does nothing if the job is not there to claim."""
    video = claim(store, video_id, worker_id)
    if video is None:
        return
    process(store, source, video, worker_id, keep_alive_s)


def process(
    store: Store,
    source: PoseSource,
    video: VideoRecord,
    worker_id: str,
    keep_alive_s: float | None = None,
) -> None:
    """Run a job this worker has already claimed."""
    video_id = video.id
    analysis_id = str(video.job.get("analysisId") or f"{_now():%Y%m%dT%H%M%S}-01")
    try:
        with (
            tempfile.TemporaryDirectory(prefix="aquatrack-job-") as tmp,
            _KeepAlive(store, video_id, worker_id, keep_alive_s) as alive,
        ):
            work = Path(tmp)
            local = work / f"video{Path(video.storage_path).suffix}"
            store.transact(
                video_id,
                lambda v: (
                    ({"job": v.job | {"poseSource": source.name}}, None)
                    if v is not None and v.job.get("leaseOwner") == worker_id
                    else (None, None)
                ),
            )
            alive.checkpoint("downloading")
            try:
                store.download_video(video.storage_path, local)
            except Exception:
                log.exception("download failed video=%s", video_id)
                return _fail(
                    store,
                    video,
                    worker_id,
                    JobError(
                        code="video_unavailable",
                        message="The uploaded video could not be loaded.",
                        retryable=True,
                    ),
                )
            alive.checkpoint("checking")
            problem = check_video_limits(local)
            if problem is not None:
                return _fail(store, video, worker_id, problem)
            try:
                identity = video_identity(local)
            except ValueError:
                return _fail(
                    store,
                    video,
                    worker_id,
                    JobError(
                        code="video_unreadable",
                        message="This file could not be read as a video.",
                        retryable=False,
                    ),
                )
            alive.checkpoint("pose")
            try:
                raw = source.get_raw_pose(local, identity, video_id)
            except PoseSourceError as e:
                return _fail(
                    store,
                    video,
                    worker_id,
                    JobError(code=e.code, message=e.message, retryable=e.retryable),
                )
            alive.checkpoint("measuring")
            result, processed = analyze(raw, video_id, video.session, identity, video_path=local)

            # Last check before anything is stored: still ours, not cancelled, not deleted.
            alive.checkpoint("saving")
            raw_path = raw.save(work / "raw_pose.npz")
            processed_path = processed.save(work / "processed_pose.npz")
            store.save_analysis(
                video,
                analysis_id,
                result.to_firestore(),
                {"raw_pose.npz": raw_path, "processed_pose.npz": processed_path},
            )
        rate = next((m.value for m in result.measurements if m.key == "stroke_rate"), None)
        done = _finish(
            store,
            video_id,
            worker_id,
            Status.READY,
            {
                "job": {"progress": None},
                "latestAnalysisId": analysis_id,
                "sha256": identity.sha256,
                "analysisSummary": {
                    "schemaVersion": result.schema_version,
                    "grade": result.quality.grade.value,
                    "validPosePct": result.quality.valid_pose_pct,
                    "strokeMeasurable": result.stroke.measurable,
                    "cyclesPerMin": rate,  # the same number the result page shows
                    "strokeCount": result.stroke.stroke_count,
                    "cycleCount": result.stroke.counted_cycles,
                    "metricsReliable": result.coverage.metrics_reliable,
                    "metricsLimited": result.coverage.metrics_limited,
                },
            },
        )
        if not done:
            # Deleted, cancelled or taken over between the save and here: what was just
            # written must not be left behind for a video that is going away.
            current = store.get_video(video_id)
            if current is None or current.status == Status.DELETING:
                store.delete_video_data(current or video)
            elif current.status == Status.ANALYZING and current.job.get("cancelRequested"):
                _cancel_now(store, video_id)
            log.info("analysis result not recorded, job no longer ours video=%s", video_id)
            return
        log.info("analysis ready video=%s grade=%s", video_id, result.quality.grade.value)
        # Interpretation is a separate step on the stored result. If it fails the analysis
        # still stands, and it can be run again without new pose inference.
        try:
            ready = store.get_video(video_id)
            if ready is not None:
                interpret_video(store, ready, analysis_id)
        except Exception:
            log.exception("interpretation failed video=%s", video_id)
    except LeaseLost:
        log.info("analysis stopped, lease lost video=%s", video_id)
    except Cancelled:
        _cancel_now(store, video_id)
        log.info("analysis cancelled video=%s", video_id)
    except TimedOut:
        _fail(
            store,
            video,
            worker_id,
            JobError(
                code="timeout",
                message="Analysing this video took too long and was stopped.",
                retryable=True,
            ),
        )
    except Exception:
        log.exception("analysis crashed video=%s", video_id)
        _fail(
            store,
            video,
            worker_id,
            JobError(
                code="internal_error",
                message="Something went wrong while analysing this video.",
                retryable=True,
            ),
        )


def _cancel_now(store: Store, video_id: str) -> None:
    def decide(video: VideoRecord | None):
        if video is None or video.status not in (Status.QUEUED, Status.ANALYZING):
            return None, None
        job = _closed(video.job, _now()) | {"progress": None}
        # A cancelled run does not use up one of the swimmer's attempts.
        job["attempts"] = max(0, int(job.get("attempts", 1) or 1) - 1)
        return {"status": Status.CANCELED.value, "job": job}, None

    store.transact(video_id, decide)


def cancel_analysis(store: Store, video_id: str, uid: str, now: datetime | None = None) -> dict:
    """Cancel the caller's own queued or running analysis. A queued job, or a running one
    whose worker has gone, is cancelled at once; a job a worker is busy with is flagged and
    the worker stops at its next checkpoint, storing nothing."""
    now = now or _now()

    def decide(video: VideoRecord | None):
        if video is None or video.uid != uid:
            raise JobRequestError(404, "Video not found.")
        if video.status not in (Status.QUEUED, Status.ANALYZING):
            raise JobRequestError(409, "This video is not being analysed.")
        if video.status == Status.ANALYZING and not _lease_expired(video.job, now):
            return {"job": video.job | {"cancelRequested": True}}, "requested"
        return None, "now"

    outcome = store.transact(video_id, decide)
    if outcome == "now":
        _cancel_now(store, video_id)
    current = store.get_video(video_id)
    return {"id": video_id, "status": current.status if current else "canceled"}


def interpret_video(
    store: Store, video: VideoRecord, analysis_id: str, explainer: Explainer | None = None
) -> Interpretation | None:
    """Interpret one stored analysis of the swimmer's own video and save the result as a new
    document. Uses only what is already stored: no video, no pose data, no model. Earlier
    swims of the same swimmer are compared when they are compatible. Returns None when the
    analysis document is missing or cannot be read."""
    stored = store.get_analysis(video.id, analysis_id)
    if stored is None or stored.get("uid") != video.uid:
        return None
    try:
        result = AnalysisResult.model_validate(stored)
    except ValueError:
        log.warning("analysis not readable for interpretation video=%s", video.id)
        return None
    history = []
    for other in store.list_videos(video.uid):
        if other.id == video.id or other.uid != video.uid or not other.latest_analysis_id:
            continue
        if other.status != Status.READY or not (other.created_at < video.created_at):
            continue  # only finished swims uploaded before this one count as "earlier"
        earlier = store.get_analysis(other.id, other.latest_analysis_id)
        if earlier is None or earlier.get("uid") != video.uid:
            continue
        try:
            history.append(
                PriorSession(
                    video_id=other.id,
                    analysis_id=other.latest_analysis_id,
                    recorded_at=other.created_at,
                    result=AnalysisResult.model_validate(earlier),
                )
            )
        except ValueError:
            continue
    history.sort(key=lambda p: p.recorded_at, reverse=True)
    profile = store.get_profile(video.uid)
    context = None
    if profile:
        goals = profile.get("goals")
        context = SwimmerContext(
            swim_level=profile.get("swim_level"),
            pbs=[p for p in profile.get("pbs") or [] if isinstance(p, dict)],
            goals=[g for g in goals if isinstance(g, str)] if isinstance(goals, list) else [],
            primary_goal=profile.get("primary_goal")
            if isinstance(profile.get("primary_goal"), str)
            else None,
        )
    found = interpret(result, video.id, analysis_id, context, history)
    interpretation_id = f"{_now():%Y%m%dT%H%M%S%f}"
    store.save_interpretation(video, interpretation_id, found.to_firestore())
    store.update_video(
        video.id,
        {
            "latestInterpretationId": interpretation_id,
            "interpretationSummary": {
                "interpretationVersion": found.interpretation_version,
                "rulesVersion": found.rules_version,
                "analysisId": analysis_id,
                "baseline": found.baseline,
                "observations": len(found.observations),
                "issueCandidates": len(found.issue_candidates),
                "priorities": len(found.priorities),
            },
        },
    )
    # Feedback is built from the interpretation just stored. It never changes a finding; a
    # failure here leaves the interpretation and the analysis as they are.
    try:
        followups = []
        if history:  # the swimmer's previous video and the checkpoints stored with it
            last = history[0]
            source = next((v for v in store.list_videos(video.uid) if v.id == last.video_id), None)
            stored = (
                store.get_feedback(last.video_id, source.latest_feedback_id)
                if source and source.latest_feedback_id
                else None
            )
            if stored and stored.get("uid") == video.uid:
                followups = comparison.follow_up(
                    [c for c in stored.get("checkpoints") or [] if isinstance(c, dict)],
                    Session(last.video_id, last.result, last.analysis_id, last.recorded_at),
                    Session(video.id, result, analysis_id, video.created_at),
                )
        feedback = build_feedback(found, interpretation_id, followups)
        feedback = explain_feedback(feedback, explainer or explainer_from_env())
        # Keyed by what the interpretation says, not by which run said it: interpreting the
        # same analysis again with nothing changed reuses the feedback already stored.
        basis = found.model_dump_json(exclude={"created_at"})
        fid = feedback_id(basis, feedback)
        store.save_feedback(video, fid, feedback.to_firestore())
        store.update_video(
            video.id,
            {
                "latestFeedbackId": fid,
                "feedbackSummary": {
                    "feedbackVersion": feedback.feedback_version,
                    "evidenceVersion": feedback.evidence_version,
                    "interpretationId": interpretation_id,
                    "explanation": feedback.explanation.source,
                    "goals": feedback.goals_used,
                    "priorities": sum(item.category == "priority" for item in feedback.items),
                },
            },
        )
    except Exception:
        log.exception("feedback failed video=%s", video.id)
    return found


def reinterpret(store: Store, video_id: str, uid: str) -> Interpretation:
    """Interpret the caller's own video again from its stored analysis."""
    video = store.get_video(video_id)
    if video is None or video.uid != uid:
        raise JobRequestError(404, "Video not found.")
    if video.status != Status.READY or not video.latest_analysis_id:
        raise JobRequestError(409, "This video has no finished analysis to interpret.")
    found = interpret_video(store, video, video.latest_analysis_id)
    if found is None:
        raise JobRequestError(409, "This video's analysis could not be read.")
    return found


def load_sessions(store: Store, uid: str) -> tuple[list[Session], list[VideoRecord]]:
    """The swimmer's own analysed videos as comparison sessions, plus all their video records."""
    videos = [v for v in store.list_videos(uid) if v.uid == uid]
    sessions = []
    for v in videos:
        if v.status != Status.READY or not v.latest_analysis_id:
            continue
        stored = store.get_analysis(v.id, v.latest_analysis_id)
        if stored is None or stored.get("uid") != uid:
            continue
        try:
            sessions.append(
                Session(
                    v.id, AnalysisResult.model_validate(stored), v.latest_analysis_id, v.created_at
                )
            )
        except ValueError:
            continue
    return sessions, videos


def compare_videos(store: Store, uid: str, first_id: str, second_id: str) -> dict:
    """Compare two of the caller's own analysed videos, the earlier one against the later."""
    sessions, videos = load_sessions(store, uid)
    owned = {v.id for v in videos}
    if first_id not in owned or second_id not in owned or first_id == second_id:
        raise JobRequestError(404, "Video not found.")
    by_id = {s.video_id: s for s in sessions}
    if first_id not in by_id or second_id not in by_id:
        raise JobRequestError(
            409, "Both videos need a finished analysis before they can be compared."
        )
    before, now = sorted((by_id[first_id], by_id[second_id]), key=lambda s: s.recorded_at)
    return comparison.compare(now, before).model_dump(mode="json")


def progress_for(store: Store, uid: str) -> dict:
    """Everything the progress page needs, computed from the swimmer's stored analyses."""
    sessions, videos = load_sessions(store, uid)
    live = [v for v in videos if v.status != Status.DELETING]
    progress = comparison.build_progress(sessions, len(live))
    by_id = {v.id: v for v in videos}
    history = []
    for s in sorted(sessions, key=lambda s: s.recorded_at):
        v = by_id[s.video_id]
        stored = (
            store.get_interpretation(v.id, v.latest_interpretation_id)
            if v.latest_interpretation_id
            else None
        )
        own = stored if stored and stored.get("uid") == uid else {}
        history.append(
            {
                "video_id": v.id,
                "recorded_at": v.created_at,
                "file_name": v.file_name,
                "observations": len(own.get("observations") or []),
                "issue_candidates": [
                    str(f.get("title", "")) for f in own.get("issue_candidates") or []
                ],
                "priorities": [str(p.get("title", "")) for p in own.get("priorities") or []],
            }
        )
    latest = max(
        (v for v in live if v.status == Status.READY and v.latest_feedback_id),
        key=lambda v: v.created_at,
        default=None,
    )
    feedback = store.get_feedback(latest.id, latest.latest_feedback_id) if latest else None
    feedback = feedback if feedback and feedback.get("uid") == uid else {}
    return {
        "progress": progress.model_dump(mode="json"),
        "history": history,
        "latest_video_id": latest.id if latest else None,
        # The newest video's checkpoints are open until a later video answers them.
        "open_checkpoints": feedback.get("checkpoints") or [],
        "followups": feedback.get("followups") or [],
    }


def delete_video(store: Store, video_id: str, uid: str) -> dict:
    """Delete one of the caller's own videos and everything stored for it. Safe to call
    again: a second call finishes what an interrupted one left, and a video that is already
    gone is reported as deleted. Someone else's video looks exactly like a missing one."""

    def decide(video: VideoRecord | None):
        if video is None:
            return None, "gone"
        if video.uid != uid:
            raise JobRequestError(404, "Video not found.")
        # From here on no analysis can start (request_analysis) or store results (run_job).
        job = {**video.job, "deleteRequestedAt": _now()}
        return {"status": Status.DELETING.value, "job": job}, "go"

    if store.transact(video_id, decide) == "gone":
        return {"deleted": True, "already_deleted": True}
    video = store.get_video(video_id)
    if video is not None:
        try:
            # Training sessions and plans are the swimmer's own and stay; only their
            # pointers to this video (and finding text copied from it) are removed.
            from aquatrack.api.training import clear_video_references

            clear_video_references(store, uid, video_id)
            store.delete_video_data(video)
        except Exception:
            log.exception("deletion incomplete video=%s", video_id)
            raise JobRequestError(
                503,
                "Some of this video's data could not be deleted yet. Nothing new will be added "
                "to it; try again to finish deleting it.",
            ) from None
    return {"deleted": True, "already_deleted": False}


class Worker:
    """Takes jobs from the queue one at a time. `run_forever` is the loop of a worker
    process; `run_once` handles at most one job and says whether there was one."""

    def __init__(self, store: Store, source: PoseSource, worker_id: str | None = None):
        self.store = store
        self.source = source
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._wake = threading.Event()
        self._stop = threading.Event()

    def run_once(self) -> bool:
        video = claim_next(self.store, self.worker_id)
        if video is None:
            return False
        process(self.store, self.source, video, self.worker_id, keep_alive_s=LEASE_S / 3)
        return True

    def run_forever(self, poll_s: float = 5.0) -> None:
        log.info("worker %s started (pose source: %s)", self.worker_id, self.source.name)
        while not self._stop.is_set():
            try:
                if self.run_once():
                    continue  # look for the next job straight away
            except Exception:  # the queue being unreachable must not kill the worker
                log.exception("worker loop error")
            self._wake.wait(poll_s)
            self._wake.clear()
        log.info("worker %s stopped", self.worker_id)

    def wake(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()


class JobRunner:
    """The API's handle on the queue. With `embedded=True` (development) a worker thread
    runs inside the API process and is woken when a job is queued; because it reads the
    same durable queue, jobs left over from before a restart are picked up again. With
    `embedded=False` the API only queues and `python -m aquatrack.worker` does the work."""

    def __init__(self, store: Store, source: PoseSource, embedded: bool = True):
        self.store = store
        self.source = source
        self.worker = Worker(store, source, f"api-{uuid.uuid4().hex[:8]}") if embedded else None
        self._thread: threading.Thread | None = None
        if self.worker:
            self._thread = threading.Thread(
                target=self.worker.run_forever, name="aquatrack-worker", daemon=True
            )
            self._thread.start()

    def submit(self, video_id: str) -> None:
        if self.worker:
            self.worker.wake()

    def shutdown(self) -> None:
        if self.worker:
            self.worker.stop()


class InlineRunner:
    """Runs the job before `submit` returns. For tests."""

    def __init__(self, store: Store, source: PoseSource):
        self.store = store
        self.source = source

    def submit(self, video_id: str) -> None:
        run_job(self.store, self.source, video_id)
