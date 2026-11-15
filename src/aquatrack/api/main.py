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
from aquatrack.api.jobs import JobRequestError, JobRunner, reinterpret, request_analysis
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
