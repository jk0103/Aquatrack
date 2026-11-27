"""FastAPI app. Run locally with: uv run uvicorn aquatrack.api.main:app --reload

Videos are uploaded by the web app straight to Firebase Storage (security rules check the
owner, type and size). This API never receives video files; it runs analysis on a video
that is already stored and writes the results back.
"""

import logging
from contextlib import asynccontextmanager
from functools import cache
from typing import Annotated

from fastapi import Body, Depends, FastAPI, HTTPException

from aquatrack import __version__
from aquatrack.analysis.explain import explainer_from_env
from aquatrack.api import account, config, demo, limits, training
from aquatrack.api.firebase import CurrentUser, delete_auth_user, sync_access_claims
from aquatrack.api.jobs import (
    JobRequestError,
    JobRunner,
    cancel_analysis,
    compare_videos,
    delete_video,
    progress_for,
    regenerate_advice,
    reinterpret,
    request_analysis,
)
from aquatrack.api.store import FirebaseStore
from aquatrack.contracts import ModelConfig

log = logging.getLogger("aquatrack.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """On start, say what is wrong with the configuration and bring up the queue handle, so
    jobs that were queued or running before a restart are picked up again."""
    for problem in config.validate("api"):
        log.error("configuration: %s", problem)
    if config.restricted():
        # The restricted security rules read a custom claim; keep it in step with the list
        # of allowed accounts. A failure leaves the door closed, never open.
        try:
            log.info("access claims: %s", sync_access_claims(config.allowed_uids()))
        except Exception as e:
            log.error("access claims not synchronised: %s", type(e).__name__)
    try:
        get_runner()
    except Exception as e:  # the API still answers /health and says why it is not ready
        log.error("job runner not started: %s", type(e).__name__)
    yield
    if get_runner.cache_info().currsize:
        get_runner().shutdown()


app = FastAPI(title="Aquatrack", version=__version__, lifespan=lifespan)


@cache
def get_runner() -> JobRunner:
    """The process-wide handle on the job queue (store + pose source), created on first
    use. In development it also runs the embedded worker thread."""
    store = FirebaseStore()
    return JobRunner(
        store,
        demo.build_pose_source(store, ModelConfig.from_env()),
        embedded=config.worker_mode() == "embedded",
    )


Runner = Annotated[JobRunner, Depends(get_runner)]


def _guard(runner: JobRunner, uid: str, bucket: str = "write") -> None:
    """Before anything that starts work or writes: the request limit, and no new work for
    an account that is being deleted."""
    limits.check(uid, bucket)
    try:
        account.guard(runner.store, uid)
    except account.AccountError as e:
        raise HTTPException(e.status_code, e.detail) from e


@app.get("/health")
def health() -> dict:
    """Liveness: the process is up. Says nothing about its dependencies."""
    return {"status": "ok", "version": __version__}


@app.get("/health/ready")
def ready() -> dict:
    """Readiness: configuration is valid and the queue can be read. Reports only counts
    and mode names: no identifiers, no secrets, no configuration values."""
    problems = config.validate("api")
    queue: dict | None = None
    try:
        pending = get_runner().store.list_pending_videos()
        queue = {
            "queued": sum(v.status == "queued" for v in pending),
            "analyzing": sum(v.status == "analyzing" for v in pending),
        }
    except Exception:
        problems.append("The job queue cannot be read.")
    if problems:
        raise HTTPException(503, {"status": "not_ready", "problems": len(problems)})
    return {
        "status": "ready",
        "environment": config.environment(),
        "access": config.access_mode(),
        "demo": config.demo_mode(),
        "worker": config.worker_mode(),
        "queue": queue,
    }


@app.delete("/me")
def delete_my_account(body: Annotated[dict, Body()], user: CurrentUser, runner: Runner) -> dict:
    """Delete the caller's account and everything it owns. Needs the confirmation phrase.
    Can be repeated safely; a repeat finishes a deletion that stopped part way."""
    limits.check(user.uid, "account")
    try:
        return account.delete_account(runner.store, user.uid, body.get("confirm"), delete_auth_user)
    except account.AccountError as e:
        raise HTTPException(e.status_code, e.detail) from e


@app.get("/me")
def me(user: CurrentUser) -> dict:
    """Who the Firebase ID token belongs to."""
    return {"uid": user.uid, "email": user.email, "name": user.name}


@app.get("/access")
def access(user: CurrentUser) -> dict:
    """What this deployment is, for a signed-in account that may use it (others get 403
    from the login check itself). The web app shows the demonstration notice from this."""
    return {"access": config.access_mode(), "demo": config.demo_mode()}


@app.post("/videos/{video_id}/analyze", status_code=202)
def analyze_video(video_id: str, user: CurrentUser, runner: Runner, rerun: bool = False) -> dict:
    """Queue analysis of one of the caller's own uploaded videos.

    Returns the job state. Asking again while a job is queued or running returns that job
    (`started` false) instead of starting a second one. Progress and results are written to
    the video's Firestore document, which the web app listens to.
    """
    _guard(runner, user.uid, "analyze")
    try:
        job = request_analysis(runner.store, video_id, user.uid, rerun=rerun)
    except JobRequestError as e:
        raise HTTPException(e.status_code, e.detail) from e
    if job.started:
        runner.submit(video_id)
    return {"id": video_id, "status": job.status, "started": job.started, "attempts": job.attempts}


@app.post("/videos/{video_id}/cancel")
def cancel_video_analysis(video_id: str, user: CurrentUser, runner: Runner) -> dict:
    """Stop the caller's own queued or running analysis. Nothing it produced is kept."""
    limits.check(user.uid, "write")
    try:
        return cancel_analysis(runner.store, video_id, user.uid)
    except JobRequestError as e:
        raise HTTPException(e.status_code, e.detail) from e


@app.post("/videos/{video_id}/advice", status_code=201)
def advise_again(video_id: str, user: CurrentUser, runner: Runner) -> dict:
    """Generate the advice of one of the caller's own analysed videos again and store it as
    a new document. With AI advice enabled this makes one model call, so it shares the
    analysis request limit; opening a result never calls a model."""
    _guard(runner, user.uid, "analyze")
    try:
        made = regenerate_advice(runner.store, video_id, user.uid)
    except JobRequestError as e:
        raise HTTPException(e.status_code, e.detail) from e
    return {
        "id": video_id,
        "adviceId": made["id"],
        "source": made.get("source"),
        "suggestions": len(made.get("suggestions") or []),
    }


@app.post("/videos/{video_id}/interpret", status_code=201)
def interpret_again(video_id: str, user: CurrentUser, runner: Runner) -> dict:
    """Read the stored analysis of one of the caller's own videos again and save a new
    interpretation next to the earlier ones. No pose inference is run."""
    _guard(runner, user.uid, "plan")
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
    limits.check(user.uid, "write")
    try:
        return delete_video(runner.store, video_id, user.uid)
    except JobRequestError as e:
        raise HTTPException(e.status_code, e.detail) from e


@app.get("/videos/{video_id}/compare/{other_id}")
def compare_two_videos(video_id: str, other_id: str, user: CurrentUser, runner: Runner) -> dict:
    """Compare two of the caller's own analysed videos, metric by metric. Computed from the
    stored analyses; nothing is stored and no pose inference is run."""
    limits.check(user.uid, "read")
    try:
        return compare_videos(runner.store, user.uid, video_id, other_id)
    except JobRequestError as e:
        raise HTTPException(e.status_code, e.detail) from e


@app.get("/progress")
def progress(user: CurrentUser, runner: Runner) -> dict:
    """The caller's sessions grouped into comparable series, with open checkpoints."""
    limits.check(user.uid, "read")
    return progress_for(runner.store, user.uid)


# ---- Training and calendar. Every route acts only on the caller's own data. Dates are the
# swimmer's local calendar dates, sent by their device; the server never converts them.

Json = Annotated[dict, Body()]


def _required(body: dict, key: str, kind: type):
    """Edits must say what they were made from; a request without it is not guessed at."""
    value = body.get(key)
    if not isinstance(value, kind) or isinstance(value, bool):
        raise HTTPException(422, f"'{key}' is required: reload and try again.")
    return value


def _training(call):
    try:
        return call()
    except training.TrainingError as e:
        raise HTTPException(e.status_code, e.detail) from e


@app.get("/training")
def training_overview(today: str, user: CurrentUser, runner: Runner) -> dict:
    """Preferences, recommendations, the activity library, active plans, this week's
    counts, upcoming sessions and training history."""
    limits.check(user.uid, "read")
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
    limits.check(user.uid, "read")
    return _training(
        lambda: training.generate(
            runner.store, user.uid, str(body.get("kind")), training.parse_date(body.get("start"))
        ).model_dump(mode="json")
    )


@app.post("/training/plans")
def save_plan(body: Json, user: CurrentUser, runner: Runner) -> dict:
    """Store the plan for these dates. If something is already planned there, the answer
    describes the conflict and nothing is stored until `confirm` is sent."""
    _guard(runner, user.uid, "plan")
    return _training(
        lambda: training.save_plan(
            runner.store,
            user.uid,
            str(body.get("kind")),
            training.parse_date(body.get("start")),
            confirm=body.get("confirm") is True,
            discard_edits=body.get("discard_edits") is True,
            explainer=explainer_from_env(),
            token=_required(body, "token", str),
        )
    )


@app.get("/training/calendar")
def training_calendar(start: str, end: str, user: CurrentUser, runner: Runner) -> dict:
    limits.check(user.uid, "read")
    return _training(
        lambda: training.calendar(
            runner.store, user.uid, training.parse_date(start), training.parse_date(end)
        )
    )


@app.post("/training/sessions", status_code=201)
def create_session(body: Json, user: CurrentUser, runner: Runner) -> dict:
    _guard(runner, user.uid)
    return _training(lambda: training.create_session(runner.store, user.uid, body))


@app.patch("/training/sessions/{session_id}")
def update_session(session_id: str, body: Json, user: CurrentUser, runner: Runner) -> dict:
    _guard(runner, user.uid)
    _required(body, "revision", int)
    return _training(lambda: training.update_session(runner.store, user.uid, session_id, body))


@app.post("/training/sessions/{session_id}/complete")
def complete_session(session_id: str, body: Json, user: CurrentUser, runner: Runner) -> dict:
    _guard(runner, user.uid)
    _required(body, "revision", int)
    return _training(lambda: training.complete_session(runner.store, user.uid, session_id, body))


@app.delete("/training/sessions/{session_id}")
def delete_session(
    session_id: str, user: CurrentUser, runner: Runner, revision: int | None = None
) -> dict:
    """Delete one training session. Videos and analyses are never touched by this."""
    limits.check(user.uid, "write")
    return _training(lambda: training.delete_session(runner.store, user.uid, session_id, revision))
