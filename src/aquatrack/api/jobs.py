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

from aquatrack.analysis import comparison
from aquatrack.analysis.comparison import Session
from aquatrack.analysis.explain import Explainer, explain_feedback, explainer_from_env
from aquatrack.analysis.feedback import build_feedback, feedback_id
from aquatrack.analysis.interpretation import PriorSession, SwimmerContext, interpret
from aquatrack.analysis.pipeline import analyze
from aquatrack.analysis.pose.sources import PoseSource, PoseSourceError
from aquatrack.analysis.video import video_identity
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
        if status == Status.DELETING:
            raise JobRequestError(409, "This video is being deleted.")
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
            result, processed = analyze(raw, video_id, video.session, identity, video_path=local)

            # The swimmer may have asked for deletion while this ran: store nothing then.
            current = store.get_video(video_id)
            if current is None or current.status != Status.ANALYZING:
                log.info("analysis dropped, video no longer waiting for it video=%s", video_id)
                return
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
        # Deletion can also arrive between the check above and the save: clean up after it.
        current = store.get_video(video_id)
        if current is None or current.status == Status.DELETING:
            store.delete_video_data(current or video)
            return
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
                    "cycleCount": result.stroke.counted_cycles,
                    "metricsReliable": result.coverage.metrics_reliable,
                    "metricsLimited": result.coverage.metrics_limited,
                },
            },
        )
        log.info("analysis ready video=%s grade=%s", video_id, result.quality.grade.value)
        # Interpretation is a separate step on the stored result. If it fails the analysis
        # still stands, and it can be run again without new pose inference.
        try:
            ready = store.get_video(video_id)
            if ready is not None:
                interpret_video(store, ready, analysis_id)
        except Exception:
            log.exception("interpretation failed video=%s", video_id)
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
