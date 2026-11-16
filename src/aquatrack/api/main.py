"""FastAPI app. Run locally with: uv run uvicorn aquatrack.api.main:app --reload

Videos are uploaded by the web app straight to Firebase Storage (security rules check the
owner, type and size). This API never receives video files; it runs analysis on a video
that is already stored and writes the results back.
"""

from functools import cache
from typing import Annotated

from fastapi import Body, Depends, FastAPI, HTTPException

from aquatrack import __version__
from aquatrack.analysis.explain import explainer_from_env
from aquatrack.analysis.pose.sources import pose_source_from_env
from aquatrack.api import training
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


# ---- Training and calendar. Every route acts only on the caller's own data. Dates are the
# swimmer's local calendar dates, sent by their device; the server never converts them.

Json = Annotated[dict, Body()]


def _training(call):
    try:
        return call()
    except training.TrainingError as e:
        raise HTTPException(e.status_code, e.detail) from e


@app.get("/training")
def training_overview(today: str, user: CurrentUser, runner: Runner) -> dict:
    """Preferences, recommendations, the activity library, active plans, this week's
    counts, upcoming sessions and training history."""
    return _training(
        lambda: training.overview(
            runner.store,
            user.uid,
            training.parse_date(today, "date"),
            llm_enabled=explainer_from_env() is not None,
        )
    )


@app.post("/training/plans/preview")
def preview_plan(body: Json, user: CurrentUser, runner: Runner) -> dict:
    """Generate a single session or a 7-day plan for review. Nothing is stored."""
    return _training(
        lambda: training.generate(
            runner.store, user.uid, str(body.get("kind")), training.parse_date(body.get("start"))
        ).model_dump(mode="json")
    )


@app.post("/training/plans")
def save_plan(body: Json, user: CurrentUser, runner: Runner) -> dict:
    """Store the plan for these dates. If something is already planned there, the answer
    describes the conflict and nothing is stored until `confirm` is sent."""
    return _training(
        lambda: training.save_plan(
            runner.store,
            user.uid,
            str(body.get("kind")),
            training.parse_date(body.get("start")),
            confirm=body.get("confirm") is True,
            discard_edits=body.get("discard_edits") is True,
            explainer=explainer_from_env(),
        )
    )


@app.get("/training/calendar")
def training_calendar(start: str, end: str, user: CurrentUser, runner: Runner) -> dict:
    return _training(
        lambda: training.calendar(
            runner.store, user.uid, training.parse_date(start), training.parse_date(end)
        )
    )


@app.post("/training/sessions", status_code=201)
def create_session(body: Json, user: CurrentUser, runner: Runner) -> dict:
    return _training(lambda: training.create_session(runner.store, user.uid, body))


@app.patch("/training/sessions/{session_id}")
def update_session(session_id: str, body: Json, user: CurrentUser, runner: Runner) -> dict:
    return _training(lambda: training.update_session(runner.store, user.uid, session_id, body))


@app.post("/training/sessions/{session_id}/complete")
def complete_session(session_id: str, body: Json, user: CurrentUser, runner: Runner) -> dict:
    return _training(lambda: training.complete_session(runner.store, user.uid, session_id, body))


@app.delete("/training/sessions/{session_id}")
def delete_session(session_id: str, user: CurrentUser, runner: Runner) -> dict:
    """Delete one training session. Videos and analyses are never touched by this."""
    return _training(lambda: training.delete_session(runner.store, user.uid, session_id))
