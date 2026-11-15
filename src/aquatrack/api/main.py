"""FastAPI app. Run locally with: uv run uvicorn aquatrack.api.main:app --reload

Videos are uploaded by the web app straight to Firebase Storage (security rules check the
owner, type and size). This API never receives video files; it runs analysis on a video
that is already stored and writes the results back.
"""

from functools import cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException

from aquatrack import __version__
from aquatrack.analysis.pose.sources import pose_source_from_env
from aquatrack.api.firebase import CurrentUser
from aquatrack.api.jobs import (
    JobRequestError,
    JobRunner,
    compare_videos,
    delete_video,
    progress_for,
    reinterpret,
    request_analysis,
)
from aquatrack.api.store import FirebaseStore
from aquatrack.contracts import ModelConfig

app = FastAPI(title="Aquatrack", version=__version__)


@cache
def get_runner() -> JobRunner:
    """The process-wide job runner (store + pose source), created on first use."""
    return JobRunner(FirebaseStore(), pose_source_from_env(ModelConfig.from_env()))


Runner = Annotated[JobRunner, Depends(get_runner)]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/me")
def me(user: CurrentUser) -> dict:
    """Who the Firebase ID token belongs to."""
    return {"uid": user.uid, "email": user.email, "name": user.name}


@app.post("/videos/{video_id}/analyze", status_code=202)
def analyze_video(video_id: str, user: CurrentUser, runner: Runner, rerun: bool = False) -> dict:
    """Queue analysis of one of the caller's own uploaded videos.

    Returns the job state. Asking again while a job is queued or running returns that job
    (`started` false) instead of starting a second one. Progress and results are written to
    the video's Firestore document, which the web app listens to.
    """
    try:
        job = request_analysis(runner.store, video_id, user.uid, rerun=rerun)
    except JobRequestError as e:
        raise HTTPException(e.status_code, e.detail) from e
    if job.started:
        runner.submit(video_id)
    return {"id": video_id, "status": job.status, "started": job.started, "attempts": job.attempts}


@app.post("/videos/{video_id}/interpret", status_code=201)
def interpret_again(video_id: str, user: CurrentUser, runner: Runner) -> dict:
    """Read the stored analysis of one of the caller's own videos again and save a new
    interpretation next to the earlier ones. No pose inference is run."""
    try:
        found = reinterpret(runner.store, video_id, user.uid)
    except JobRequestError as e:
        raise HTTPException(e.status_code, e.detail) from e
    return {
        "id": video_id,
        "analysisId": found.analysis_id,
        "rulesVersion": found.rules_version,
        "baseline": found.baseline,
        "observations": len(found.observations),
        "issueCandidates": len(found.issue_candidates),
        "priorities": len(found.priorities),
    }


@app.delete("/videos/{video_id}")
def delete_own_video(video_id: str, user: CurrentUser, runner: Runner) -> dict:
    """Delete one of the caller's own videos with its analyses, pose data, interpretations
    and feedback. Can be repeated safely. Storage paths are never returned."""
    try:
        return delete_video(runner.store, video_id, user.uid)
    except JobRequestError as e:
        raise HTTPException(e.status_code, e.detail) from e


@app.get("/videos/{video_id}/compare/{other_id}")
def compare_two_videos(video_id: str, other_id: str, user: CurrentUser, runner: Runner) -> dict:
    """Compare two of the caller's own analysed videos, metric by metric. Computed from the
    stored analyses; nothing is stored and no pose inference is run."""
    try:
        return compare_videos(runner.store, user.uid, video_id, other_id)
    except JobRequestError as e:
        raise HTTPException(e.status_code, e.detail) from e


@app.get("/progress")
def progress(user: CurrentUser, runner: Runner) -> dict:
    """The caller's sessions grouped into comparable series, with open checkpoints."""
    return progress_for(runner.store, user.uid)
