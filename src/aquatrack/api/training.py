"""Training plans, sessions and the calendar: storage, ownership and edit rules.

Everything is written by this backend after checking the owner; the security rules let a
swimmer read their own training documents and write none. Plans come from the deterministic
planner (`aquatrack.training.planner`); this module never generates content itself.

Dates are the swimmer's local calendar dates ("YYYY-MM-DD") and optional local times
("HH:MM"), stored as typed and never converted between time zones. "Today" is supplied by
the swimmer's device. A session is completed only when the swimmer says so.
"""

import logging
import re
import uuid
from datetime import date, timedelta

from aquatrack.api.store import Store
from aquatrack.contracts import AnalysisJobStatus as Status
from aquatrack.training import library, planner
from aquatrack.training.explain import explain_plan
from aquatrack.training.models import (
    TRAINING_VERSION,
    Completion,
    PlanItem,
    PlannedSession,
    Swimmer,
    TrainingPlan,
)
from aquatrack.training.models import _now as _now
from aquatrack.training.planner import AnalysisContext, History

log = logging.getLogger("aquatrack.training")

PLANS, SESSIONS = "training_plans", "training_sessions"
MAX_ITEMS = 12
MAX_SESSION_MIN = 180
MAX_TITLE, MAX_NOTE, MAX_CUSTOM_NAME = 80, 300, 60
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
REMOVED_REASON = (
    "The video this was based on has been deleted. The activity stays in your plan as "
    "general practice."
)


class TrainingError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def parse_date(value: object, what: str = "date") -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise TrainingError(422, f"Enter the {what} as YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise TrainingError(422, f"That {what} is not a real calendar date.") from None


# ---------------------------------------------------------------- what the plan may use


def _live_videos(store: Store, uid: str) -> list:
    return [v for v in store.list_videos(uid) if v.status != Status.DELETING]


def analysis_context(store: Store, uid: str) -> AnalysisContext:
    """What the swimmer's newest analysed video supports, read from what is stored. A
    finding counts only if the feedback shows it as a focus or priority and its rule is one
    the planner has practice for. Nothing is recomputed and nothing is added."""
    ready = [
        v for v in _live_videos(store, uid) if v.status == Status.READY and v.latest_analysis_id
    ]
    if not ready:
        return AnalysisContext()
    video = max(ready, key=lambda v: v.created_at)
    ctx = AnalysisContext(video_id=video.id, analysis_id=video.latest_analysis_id)
    analysis = store.get_analysis(video.id, video.latest_analysis_id) or {}
    if analysis.get("uid") != uid or not any(
        m.get("status") == "reliable" for m in analysis.get("metrics") or []
    ):
        ctx.state = "unavailable"
        return ctx
    feedback = (
        store.get_feedback(video.id, video.latest_feedback_id) if video.latest_feedback_id else None
    ) or {}
    found = (
        store.get_interpretation(video.id, video.latest_interpretation_id)
        if video.latest_interpretation_id
        else None
    ) or {}
    if feedback.get("uid") != uid or found.get("uid") != uid:
        ctx.state = "unavailable"
        return ctx
    ctx.feedback_id = video.latest_feedback_id
    rules = {f.get("id"): f for f in found.get("issue_candidates") or []}
    for item in feedback.get("items") or []:
        finding = rules.get(item.get("finding_id"))
        if (
            item.get("category") in ("focus", "priority")
            and finding
            and finding.get("rule_id") in planner.RULE_ACTIVITIES
        ):
            ctx.findings.append(
                {
                    "id": str(finding["id"]),
                    "rule_id": str(finding["rule_id"]),
                    "title": str(finding.get("title", "")),
                }
            )
    ctx.checkpoints = [
        {
            "id": str(c.get("id", "")),
            "title": str(c.get("title", "")),
            "what_to_film": str(c.get("what_to_film", "")),
        }
        for c in feedback.get("checkpoints") or []
    ]
    ctx.state = "supported" if ctx.findings else "no_supported_issue"
    return ctx


def _sessions(store: Store, uid: str) -> list[PlannedSession]:
    out = []
    for doc in store.list_docs(SESSIONS, uid):
        try:
            out.append(PlannedSession.model_validate({k: v for k, v in doc.items() if k != "uid"}))
        except Exception:  # an unreadable document is skipped, never guessed at
            log.warning("unreadable training session skipped")
    return sorted(out, key=lambda s: (s.date, s.time, s.created_at))


def _plans(store: Store, uid: str) -> list[TrainingPlan]:
    out = []
    for doc in store.list_docs(PLANS, uid):
        try:
            out.append(TrainingPlan.model_validate({k: v for k, v in doc.items() if k != "uid"}))
        except Exception:
            log.warning("unreadable training plan skipped")
    return sorted(out, key=lambda p: (p.start_date, p.version, p.created_at))


def _save_session(store: Store, uid: str, session: PlannedSession) -> None:
    session.minutes = sum(i.minutes for i in session.items)
    session.distance_m = sum(i.distance_m or 0 for i in session.items) or None
    levels = [i.intensity for i in session.items]
    session.intensity = next((x for x in ("brisk", "moderate", "easy") if x in levels), "")
    store.set_doc(SESSIONS, session.id, {**session.model_dump(mode="json"), "uid": uid})


def _save_plan(store: Store, uid: str, plan: TrainingPlan) -> None:
    doc = plan.model_dump(mode="json", exclude={"sessions"})
    store.set_doc(PLANS, plan.id, {**doc, "uid": uid})


def _own_session(store: Store, uid: str, session_id: str) -> PlannedSession:
    doc = store.get_doc(SESSIONS, session_id)
    if doc is None or doc.get("uid") != uid:  # someone else's looks exactly like a missing one
        raise TrainingError(404, "Session not found.")
    return PlannedSession.model_validate({k: v for k, v in doc.items() if k != "uid"})


def history(sessions: list[PlannedSession], today: date) -> History:
    recent = (today - timedelta(14)).isoformat()
    return History(
        completed=sum(s.status == "completed" for s in sessions),
        recent_completed=sum(s.status == "completed" and s.date >= recent for s in sessions),
        recent_skipped=sum(s.status == "skipped" and s.date >= recent for s in sessions),
    )


def _swimmer(store: Store, uid: str) -> Swimmer:
    return planner.swimmer_from_profile(store.get_profile(uid))


def generate(store: Store, uid: str, kind: str, start: date) -> TrainingPlan:
    if kind not in ("session", "week"):
        raise TrainingError(422, "Choose a single session or a weekly plan.")
    swimmer = _swimmer(store, uid)
    if swimmer.session_minutes is not None and swimmer.session_minutes < planner.MIN_SESSION_MIN:
        raise TrainingError(
            422,
            f"A planned session needs at least {planner.MIN_SESSION_MIN} minutes. "
            "Change the time per session in your training preferences.",
        )
    ctx = analysis_context(store, uid)
    past = history(_sessions(store, uid), start)
    build = planner.build_week if kind == "week" else planner.build_single
    return build(swimmer, ctx, start, past)


# ---------------------------------------------------------------- reading


def _public(session: PlannedSession, live: set[str]) -> dict:
    """A session as the swimmer sees it. A link to a video that no longer exists is never
    returned, whatever is still stored."""
    data = session.model_dump(mode="json")
    if data["linked_video_id"] and data["linked_video_id"] not in live:
        data["linked_video_id"], data["linked_video_removed"] = "", True
    cp = data.get("checkpoint")
    if cp and cp["source_video_id"] and cp["source_video_id"] not in live:
        cp["source_video_id"], cp["checkpoint_ids"] = "", []
    return data


def _public_plan(plan: TrainingPlan, sessions: list[PlannedSession], live: set[str]) -> dict:
    data = plan.model_dump(mode="json", exclude={"sessions"})
    if data["inputs"]["video_id"] and data["inputs"]["video_id"] not in live:
        _strip_analysis(data)
    data["sessions"] = [
        _public(s, live) for s in sessions if s.plan_id == plan.id and s.status != "replaced"
    ]
    return data


def _strip_analysis(plan: dict) -> None:
    plan["inputs"].update(video_id="", analysis_id="", feedback_id="", analysis_removed=True)
    for rec in plan.get("recommendations") or []:
        if rec.get("video_id") or rec.get("finding_ids"):
            rec.update(
                video_id="",
                analysis_id="",
                finding_ids=[],
                finding_titles=[],
                reason=REMOVED_REASON,
            )


def week_of(today: date) -> tuple[date, date]:
    start = today - timedelta(today.weekday())  # Monday
    return start, start + timedelta(6)


def overview(store: Store, uid: str, today: date, llm_enabled: bool = False) -> dict:
    """Everything the Training page, the Home page and the Progress page need."""
    swimmer = _swimmer(store, uid)
    ctx = analysis_context(store, uid)
    live = {v.id for v in _live_videos(store, uid)}
    sessions = [s for s in _sessions(store, uid) if s.status != "replaced"]
    plans = [p for p in _plans(store, uid) if p.status == "active"]
    start, end = week_of(today)
    in_week = [s for s in sessions if start.isoformat() <= s.date <= end.isoformat()]
    done = [s for s in sessions if s.status in ("completed", "skipped", "canceled")]
    return {
        "training_version": TRAINING_VERSION,
        "library_version": library.LIBRARY_VERSION,
        "swimmer": swimmer.model_dump(mode="json"),
        "analysis": {
            "state": ctx.state,
            "video_id": ctx.video_id,
            "findings": [{"id": f["id"], "title": f["title"]} for f in ctx.findings],
            "checkpoints": ctx.checkpoints,
        },
        "recommendations": [r.model_dump(mode="json") for r in planner.recommend(swimmer, ctx)],
        "library": [
            {
                **a.model_dump(mode="json"),
                "not_offered": library.eligible(a, swimmer.level, swimmer.equipment),
            }
            for a in library.active()
        ],
        "sources": [s.model_dump(mode="json") for s in library.SOURCES.values()],
        "plans": [_public_plan(p, sessions, live) for p in reversed(plans)][:8],
        "week": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "planned": sum(s.status == "planned" for s in in_week),
            "completed": sum(s.status == "completed" for s in in_week),
            "skipped": sum(s.status == "skipped" for s in in_week),
            "canceled": sum(s.status == "canceled" for s in in_week),
        },
        "upcoming": [
            _public(s, live)
            for s in sessions
            if s.status == "planned" and s.date >= today.isoformat()
        ][:6],
        "history": [_public(s, live) for s in reversed(done)][:30],
        "totals": {
            "completed": sum(s.status == "completed" for s in sessions),
            "skipped": sum(s.status == "skipped" for s in sessions),
        },
        "llm_enabled": llm_enabled,
    }


def calendar(store: Store, uid: str, start: date, end: date) -> dict:
    if end < start or (end - start).days > 100:
        raise TrainingError(422, "Ask for a period of up to 100 days.")
    live_videos = _live_videos(store, uid)
    live = {v.id for v in live_videos}
    lo, hi = start.isoformat(), end.isoformat()
    sessions = [s for s in _sessions(store, uid) if s.status != "replaced" and lo <= s.date <= hi]
    taken = {s.date for s in sessions if s.status != "canceled"}
    rest = {}
    for plan in _plans(store, uid):
        if plan.status == "active":
            for day in plan.rest_days:
                if lo <= day.date <= hi and day.date not in taken:
                    rest[day.date] = {
                        "date": day.date,
                        "guidance": day.guidance,
                        "plan_id": plan.id,
                    }
    return {
        "sessions": [_public(s, live) for s in sessions],
        "rest_days": [rest[d] for d in sorted(rest)],
        # For linking a completed session to one of the swimmer's own videos.
        "videos": [
            {"id": v.id, "file_name": v.file_name, "recorded_at": v.created_at}
            for v in sorted(live_videos, key=lambda v: v.created_at, reverse=True)
        ][:30],
    }


# ---------------------------------------------------------------- saving a generated plan


def save_plan(
    store: Store,
    uid: str,
    kind: str,
    start: date,
    confirm: bool = False,
    discard_edits: bool = False,
    explainer=None,
) -> dict:
    """Store a generated plan and its sessions. Never silently replaces anything: if these
    dates already hold a plan or a planned session, the answer describes the conflict and
    nothing is stored until the swimmer confirms. Sessions the swimmer edited, completed,
    skipped or cancelled are kept (edited ones unless `discard_edits`)."""
    plan = generate(store, uid, kind, start)
    sessions = _sessions(store, uid)
    live = {v.id for v in _live_videos(store, uid)}
    old_plans = [
        p
        for p in _plans(store, uid)
        if p.status == "active"
        and p.kind == "week"
        and kind == "week"
        and p.start_date <= plan.end_date
        and plan.start_date <= p.end_date
    ]
    same_day = [
        s
        for s in sessions
        if kind == "session" and s.status == "planned" and s.date == plan.start_date
    ]
    if (old_plans or same_day) and not confirm:
        return {
            "saved": False,
            "conflict": {
                "kind": "week_overlap" if old_plans else "date_has_session",
                "plans": [
                    {
                        "id": p.id,
                        "title": p.title,
                        "version": p.version,
                        "edited": sum(
                            s.plan_id == p.id and s.status == "planned" and s.edited
                            for s in sessions
                        ),
                        "unedited": sum(
                            s.plan_id == p.id and s.status == "planned" and not s.edited
                            for s in sessions
                        ),
                        "recorded": sum(
                            s.plan_id == p.id and s.status in ("completed", "skipped", "canceled")
                            for s in sessions
                        ),
                    }
                    for p in old_plans
                ],
                "sessions": [{"id": s.id, "title": s.title, "date": s.date} for s in same_day],
            },
        }
    plan.id = uuid.uuid4().hex
    plan.series_id = old_plans[0].series_id if old_plans else plan.id
    plan.version = max((p.version for p in old_plans), default=0) + 1
    plan.status = "active"
    kept_dates: set[str] = set()
    for old in old_plans:
        for s in sessions:
            if s.plan_id != old.id or s.status == "replaced":
                continue
            if s.status == "planned" and (not s.edited or discard_edits):
                s.status = "replaced"  # kept in storage as part of the old version
                _save_session(store, uid, s)
            else:
                kept_dates.add(s.date)
        old.status, old.replaced_by = "replaced", plan.id
        _save_plan(store, uid, old)
    fresh = []
    for s in plan.sessions:
        if s.date in kept_dates:  # the swimmer's own version of that day stays
            plan.notes.append(f"Kept the session you already had on {s.date}.")
            continue
        s.id, s.plan_id, s.plan_version = uuid.uuid4().hex, plan.id, plan.version
        fresh.append(s)
    plan.sessions = fresh
    plan = explain_plan(plan, explainer)
    for s in fresh:
        _save_session(store, uid, s)
    _save_plan(store, uid, plan)
    return {"saved": True, "plan": _public_plan(plan, fresh, live)}


# ---------------------------------------------------------------- the swimmer's own edits


def _items(raw: object, swimmer: Swimmer, before: list[PlanItem]) -> list[PlanItem]:
    """Check an edited activity list and rebuild it from the library. Records, per activity,
    whether it is still as recommended, was changed by the swimmer, or was added by them."""
    if not isinstance(raw, list) or not raw:
        raise TrainingError(422, "A session needs at least one activity.")
    if len(raw) > MAX_ITEMS:
        raise TrainingError(422, f"A session can hold up to {MAX_ITEMS} activities.")
    earlier = {i.activity_id: i for i in before if i.activity_id}
    custom_before = {i.name: i for i in before if not i.activity_id}
    out: list[PlanItem] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise TrainingError(422, "That activity list could not be read.")
        minutes = entry.get("minutes")
        if not isinstance(minutes, int) or isinstance(minutes, bool):
            raise TrainingError(422, "Give each activity a whole number of minutes.")
        activity_id = entry.get("activity_id") or ""
        if not activity_id:
            name = str(entry.get("name") or "").strip()
            if not name or len(name) > MAX_CUSTOM_NAME:
                raise TrainingError(
                    422, f"Name your own activity in up to {MAX_CUSTOM_NAME} characters."
                )
            if not 1 <= minutes <= 120:
                raise TrainingError(422, f"{name}: choose between 1 and 120 minutes.")
            done = bool(custom_before[name].done) if name in custom_before else False
            out.append(
                PlanItem(name=name, category="custom", minutes=minutes, source="manual", done=done)
            )
            continue
        activity = library.ACTIVITIES.get(activity_id)
        if activity is None:
            raise TrainingError(422, "That activity is not in the library.")
        if activity_id in seen:
            raise TrainingError(
                422, f"{activity.name} is listed twice. Change its minutes instead."
            )
        seen.add(activity_id)
        old = earlier.get(activity_id)
        if old is None:  # only newly added activities are checked against level and kit
            reason = library.eligible(activity, swimmer.level, swimmer.equipment)
            if reason:
                raise TrainingError(422, reason)
        if not activity.min_minutes <= minutes <= activity.max_minutes:
            raise TrainingError(
                422,
                f"{activity.name}: choose between {activity.min_minutes} and "
                f"{activity.max_minutes} minutes.",
            )
        item = planner._item(activity_id, minutes, swimmer)
        if old is None:
            item.source = "manual"
        else:
            item.done = old.done
            item.recommendation_id, item.basis = old.recommendation_id, old.basis
            item.source = (
                old.source if old.minutes == minutes or old.source == "manual" else "modified"
            )
        out.append(item)
    total = sum(i.minutes for i in out)
    if total > MAX_SESSION_MIN:
        raise TrainingError(
            422, f"That adds up to {total} minutes; keep a session under {MAX_SESSION_MIN}."
        )
    brisk = [i for i in out if i.intensity == "brisk"]
    if len(brisk) > 1:
        raise TrainingError(422, "Keep to one brisk activity in a session.")
    if brisk and not any(i.category == "warm_up" for i in out[: out.index(brisk[0])]):
        raise TrainingError(422, f"{brisk[0].name} needs a warm-up before it.")
    return out


def _schedule(session: PlannedSession, body: dict) -> None:
    if "date" in body:
        session.date = parse_date(body["date"]).isoformat()
    if "time" in body:
        value = body["time"] or ""
        if value and not (isinstance(value, str) and TIME.match(value)):
            raise TrainingError(422, "Enter the time as HH:MM, or leave it empty.")
        session.time = value
    if "title" in body:
        title = str(body["title"] or "").strip()
        if not title or len(title) > MAX_TITLE:
            raise TrainingError(422, f"Give the session a title of up to {MAX_TITLE} characters.")
        session.title = title


def create_session(store: Store, uid: str, body: dict) -> dict:
    """A session the swimmer writes themself. Nothing in it is marked as recommended."""
    if "date" not in body or "title" not in body:
        raise TrainingError(422, "A session needs a date and a title.")
    session = PlannedSession(date="2000-01-01", title="-", origin="manual", basis=None)
    _schedule(session, body)
    session.items = _items(body.get("items"), _swimmer(store, uid), [])
    for item in session.items:
        item.source = "manual"
    twin = [
        s
        for s in _sessions(store, uid)
        if s.status == "planned"
        and (s.date, s.time, s.title.lower()) == (session.date, session.time, session.title.lower())
    ]
    if twin and not body.get("allow_duplicate"):
        raise TrainingError(409, "You already have a session with this title at that time.")
    session.id = uuid.uuid4().hex
    session.safety = list(planner.SAFETY)
    _save_session(store, uid, session)
    return _public(session, {v.id for v in _live_videos(store, uid)})


def update_session(store: Store, uid: str, session_id: str, body: dict) -> dict:
    """Reschedule, retitle, change the activities, or skip / cancel / reopen a session."""
    session = _own_session(store, uid, session_id)
    if session.status == "replaced":
        raise TrainingError(409, "This session belongs to a plan version that was replaced.")
    before = (session.date, session.time, session.title, [i.model_dump() for i in session.items])
    _schedule(session, body)
    if "items" in body:
        if session.status == "completed":
            raise TrainingError(409, "Reopen the session before changing its activities.")
        session.items = _items(body["items"], _swimmer(store, uid), session.items)
    if "status" in body:
        status = body["status"]
        if status not in ("planned", "skipped", "canceled"):
            raise TrainingError(422, "A session can be planned, skipped or cancelled here.")
        if status == "planned":  # reopening clears the completion the swimmer recorded
            session.completion = None
            for item in session.items:
                item.done = False
        session.status = status
    after = (session.date, session.time, session.title, [i.model_dump() for i in session.items])
    if after != before:
        session.edited = True
    session.updated_at = _now()
    _save_session(store, uid, session)
    return _public(session, {v.id for v in _live_videos(store, uid)})


def complete_session(store: Store, uid: str, session_id: str, body: dict) -> dict:
    """Record that the swimmer did a session: which activities, when, and an optional note
    and video link. Only ever called by the swimmer; time passing completes nothing."""
    session = _own_session(store, uid, session_id)
    if session.status in ("replaced", "canceled"):
        raise TrainingError(409, "A cancelled or replaced session cannot be completed.")
    on = parse_date(body.get("completed_on"), "completion date")
    note = str(body.get("note") or "").strip()
    if len(note) > MAX_NOTE:
        raise TrainingError(422, f"Keep the note under {MAX_NOTE} characters.")
    done = body.get("done", list(range(len(session.items))))
    if not isinstance(done, list) or any(
        not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(session.items)
        for i in done
    ):
        raise TrainingError(422, "That list of completed activities does not match the session.")
    live = {v.id for v in _live_videos(store, uid)}
    video_id = str(body.get("video_id") or "")
    if video_id and video_id not in live:  # includes other swimmers' videos
        raise TrainingError(404, "Video not found.")
    for n, item in enumerate(session.items):
        item.done = n in done
    session.status = "completed"
    session.completion = Completion(completed_on=on.isoformat(), note=note)
    session.linked_video_id, session.linked_video_removed = video_id, False
    session.updated_at = session.completion.recorded_at
    _save_session(store, uid, session)
    return _public(session, live)


def delete_session(store: Store, uid: str, session_id: str) -> dict:
    """Remove one training session. This never touches a video or an analysis."""
    doc = store.get_doc(SESSIONS, session_id)
    if doc is None:
        return {"deleted": True, "already_deleted": True}
    if doc.get("uid") != uid:
        raise TrainingError(404, "Session not found.")
    store.delete_doc(SESSIONS, session_id)
    return {"deleted": True, "already_deleted": False}


# ---------------------------------------------------------------- when a video is deleted


def clear_video_references(store: Store, uid: str, video_id: str) -> int:
    """Remove every pointer from training data to a video that is being deleted, and the
    finding text copied from its analysis. The swimmer's sessions, notes and completion
    history stay: deleting a video is not deleting training. Safe to run again."""
    changed = 0
    for doc in store.list_docs(SESSIONS, uid):
        touched = False
        if doc.get("linked_video_id") == video_id:
            doc["linked_video_id"], doc["linked_video_removed"] = "", True
            touched = True
        cp = doc.get("checkpoint")
        if cp and cp.get("source_video_id") == video_id:
            cp["source_video_id"], cp["checkpoint_ids"] = "", []
            touched = True
        if touched:
            store.set_doc(SESSIONS, doc["id"], doc)
            changed += 1
    for doc in store.list_docs(PLANS, uid):
        if (doc.get("inputs") or {}).get("video_id") == video_id:
            _strip_analysis(doc)
            store.set_doc(PLANS, doc["id"], doc)
            changed += 1
            for s in store.list_docs(SESSIONS, uid):
                if s.get("plan_id") == doc["id"] and s.get("finding_ids"):
                    s["finding_ids"] = []
                    store.set_doc(SESSIONS, s["id"], s)
    return changed
