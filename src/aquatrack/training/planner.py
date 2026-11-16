"""The deterministic training planner. No language model, no randomness: the same inputs
always give the same plan.

What it will not do:
- invent a technique problem. An activity is linked to the swimmer's analysis only when the
  stored interpretation holds a supported finding (a focus or priority) whose rule is
  mapped below. Otherwise the plan is goal-based (or general) and says so.
- go beyond what the swimmer said: never more sessions, days or minutes than their settings.
- raise the load by itself. History only rotates which practice comes first.
"""
# ruff: noqa: E501

from dataclasses import dataclass, field
from datetime import date, timedelta

from aquatrack.training import library
from aquatrack.training.models import (
    DAYS,
    DIFFICULTIES,
    EQUIPMENT,
    STROKES,
    TIMES_OF_DAY,
    PlanInputs,
    PlanItem,
    PlannedSession,
    Recommendation,
    RestDay,
    SessionCheckpoint,
    Swimmer,
    TrainingPlan,
)

MIN_SESSION_MIN = 15
DEFAULT_SESSION_MIN = 30  # used only when the swimmer gave no session length
DEFAULT_SESSIONS = 2  # used only when the swimmer gave no weekly frequency
MAX_SESSIONS_PER_WEEK = 6  # always leaves a day without swimming
# Longest session the planner will write by itself. The swimmer can lengthen it by hand.
SESSION_CAP = {"beginner": 45, "hobby": 60, "masters": 90, "competitive": 90}
BEGINNER_MAX_SESSIONS = 4
# Minutes per 50 m including rest, for the "about N x 50 m" guide only. Engineering
# assumptions, set at or below the 1,000 to 1,500 yards per 30 minutes a masters coach
# article gives for adult swimmers (library source usms_30min). Time is what the plan fixes.
PACE_MIN_PER_50 = {"beginner": 2.5, "hobby": 1.75, "masters": 1.4, "competitive": 1.25}

GOAL_LABELS = {
    "stroke_consistency": "stroke consistency",
    "body_alignment": "body alignment",
    "arm_technique": "arm technique",
    "speed": "swimming speed",
    "endurance": "endurance",
    "breathing": "breathing",
    "overall_freestyle": "overall freestyle",
}
# Technique practice per goal, in the order tried.
GOAL_ACTIVITIES = {
    "stroke_consistency": ["tech.count_strokes", "tech.even_pace"],
    "body_alignment": ["tech.head_still", "tech.side_kick"],
    "arm_technique": ["tech.catch_up", "tech.count_strokes"],
    "speed": ["tech.even_pace", "tech.count_strokes"],
    "endurance": ["tech.even_pace", "tech.breathe_every_three"],
    "breathing": ["tech.kickboard_breathing", "tech.breathe_every_three"],
    "overall_freestyle": ["tech.head_still", "tech.count_strokes", "tech.side_kick"],
}
GENERAL_ACTIVITIES = ["tech.head_still", "tech.count_strokes"]
# Supported interpretation rules -> practice that may be linked to them. Only rules that are
# active in analysis/interpretation.py appear here; a pending rule can never reach a plan.
RULE_ACTIVITIES = {
    "timing.uneven_rhythm": ["tech.count_strokes", "tech.even_pace"],
    "history.rhythm_less_steady": ["tech.count_strokes", "tech.even_pace"],
}

SAFETY = [
    "Stop and rest if you feel dizzy, unusually short of breath or unwell.",
    "Breathe whenever you need to. Never hold your breath or limit your breathing on purpose.",
    "This is a suggestion, not a prescription. Shorten or skip anything that does not feel right.",
]
YOUNG_NOTE = "For a younger swimmer this plan stays general and easy to moderate. Swim where a lifeguard, teacher or responsible adult is present."
REST_DAY = "No swimming planned. Rest, or do something light that you enjoy."
PLAN_LIMITS = [
    "No source in the library shows that this plan improves a particular swimmer's technique or times.",
    "Distances and repeats are rough guides from assumed paces; the time is what the plan fixes.",
    "Completing sessions is recorded as adherence only. It is never read as a technique change.",
]


@dataclass
class AnalysisContext:
    """What the swimmer's latest analysed video supports, as stored. Nothing is recomputed."""

    state: str = "none"  # none | unavailable | no_supported_issue | supported
    video_id: str = ""
    analysis_id: str = ""
    feedback_id: str = ""
    # supported findings only: {"id", "rule_id", "title"}
    findings: list[dict] = field(default_factory=list)
    # open next-video checkpoints: {"id", "title", "what_to_film"}
    checkpoints: list[dict] = field(default_factory=list)


@dataclass
class History:
    completed: int = 0  # sessions the swimmer marked completed, ever
    recent_completed: int = 0  # in the last 14 days
    recent_skipped: int = 0


def swimmer_from_profile(profile: dict | None) -> Swimmer:
    """Read the profile's own answers. Anything missing stays missing: it is listed in
    `missing` and never guessed (a personal best says nothing about level here)."""
    p = profile or {}
    t = p.get("training") if isinstance(p.get("training"), dict) else {}

    def number(value, lo, hi):
        return int(value) if isinstance(value, int | float) and lo <= value <= hi else None

    level = p.get("swim_level") if p.get("swim_level") in SESSION_CAP else None
    sessions = number(p.get("sessions_per_week"), 1, 14)
    minutes = number(p.get("minutes_per_day"), 1, 600)
    days = [d for d in DAYS if d in (t.get("days") or [])]
    goals = [g for g in (p.get("goals") or []) if g in GOAL_LABELS]
    primary = p.get("primary_goal") if p.get("primary_goal") in goals else None
    s = Swimmer(
        level=level,
        age=number(p.get("age"), 5, 100),
        sessions_per_week=sessions,
        session_minutes=minutes,
        days=days,
        time_of_day=t.get("time_of_day") if t.get("time_of_day") in TIMES_OF_DAY else "",
        typical_distance_m=number(t.get("typical_distance_m"), 100, 10000),
        strokes=[x for x in STROKES if x in (t.get("strokes") or [])],
        equipment=[e for e in EQUIPMENT if e in (t.get("equipment") or [])],
        difficulty=t.get("difficulty") if t.get("difficulty") in DIFFICULTIES else "",
        goals=goals,
        primary_goal=primary or (goals[0] if len(goals) == 1 else None),
    )
    s.missing = [
        label
        for label, absent in [
            ("swimming level", level is None),
            ("sessions per week", sessions is None),
            ("time per session", minutes is None),
            ("available days", not days),
            ("goals", not goals),
            ("preferred difficulty", not s.difficulty),
        ]
        if absent
    ]
    return s


def _level(s: Swimmer) -> str:
    return s.level or "beginner"  # unknown experience is planned as a beginner


def _difficulty(s: Swimmer) -> str:
    """The swimmer's choice, lowered where the context calls for caution. Never raised."""
    chosen = s.difficulty or ("easy" if _level(s) == "beginner" else "moderate")
    if s.level is None or (s.age is not None and s.age < 13):
        return "easy"
    if chosen == "challenging" and (
        _level(s) not in ("masters", "competitive") or (s.age is not None and s.age < 18)
    ):
        return "moderate"
    return chosen


def session_minutes(s: Swimmer) -> tuple[int, list[str]]:
    """Minutes the planner will fill, and what it assumed. Never above the swimmer's own."""
    notes = []
    cap = SESSION_CAP[_level(s)]
    if s.age is not None and s.age < 13:
        cap = min(cap, 45)
    elif s.age is not None and s.age < 18:
        cap = min(cap, 60)
    if s.session_minutes is None:
        notes.append(
            f"You have not said how long a session can be, so this uses {DEFAULT_SESSION_MIN} minutes."
        )
        return min(DEFAULT_SESSION_MIN, cap), notes
    if s.session_minutes > cap:
        notes.append(
            f"You have {s.session_minutes} minutes available; the plan fills {cap} as a conservative choice. You can lengthen a session yourself."
        )
        return cap, notes
    return s.session_minutes, notes


def _split(total: int, kind: str) -> tuple[int, int, list[int], int]:
    """(warm-up, cool-down, technique blocks, main set) in minutes; they add up to `total`."""
    warm = 5 if total < 30 else 10 if total < 75 else 15
    cool = 5 if total < 60 else 10
    rest = total - warm - cool
    if rest < 10:
        return warm, cool, [], rest
    # A technique session spends more of its time on practice; the others keep one reminder.
    blocks = 1 if rest < 25 or kind != "technique" else 2 if rest < 45 else 3
    each = 5 if rest < 30 else 10
    while blocks and rest - blocks * each < 5:
        blocks -= 1
    return warm, cool, [each] * blocks, rest - blocks * each


def _item(
    activity_id: str, minutes: int, s: Swimmer, rec: Recommendation | None = None
) -> PlanItem:
    a = library.ACTIVITIES[activity_id]
    minutes = max(1, minutes)
    sets, distance = "", None
    if a.repeat_m:
        per_repeat = PACE_MIN_PER_50[_level(s)] * a.repeat_m / 50
        reps = max(1, int(minutes / per_repeat))
        distance = reps * a.repeat_m
        sets = f"about {reps} x {a.repeat_m} m"
    return PlanItem(
        activity_id=a.id,
        name=a.name,
        category=a.category,
        minutes=minutes,
        distance_m=distance,
        sets=sets,
        intensity=a.intensity,
        rest=a.rest,
        instructions=list(a.instructions),
        equipment=list(a.equipment),
        safety=list(a.safety),
        source="recommended",
        recommendation_id=rec.id if rec else "",
        basis=rec.basis if rec else None,
        evidence_class=a.evidence_class,
    )


_RANK = {"easy": 0, "moderate": 1, "brisk": 2, "challenging": 2}


def _usable(ids: list[str], s: Swimmer) -> list[str]:
    """Activities the swimmer can be offered: right level, kit they have, and no harder
    than the difficulty the plan is allowed to use."""
    cap = _RANK[_difficulty(s)]
    return [
        i
        for i in ids
        if library.eligible(library.ACTIVITIES[i], _level(s), s.equipment) is None
        and _RANK[library.ACTIVITIES[i].intensity] <= cap
    ]


def recommend(s: Swimmer, ctx: AnalysisContext) -> list[Recommendation]:
    """Technique practice the swimmer can be offered, most relevant first, each with the
    reason and what it rests on. Analysis-based entries exist only for supported findings."""
    recs: list[Recommendation] = []
    seen: set[str] = set()

    def add(activity_id, basis, reason, inputs, **kw):
        if activity_id in seen:
            return
        seen.add(activity_id)
        a = library.ACTIVITIES[activity_id]
        recs.append(
            Recommendation(
                id=f"rec.{basis}.{activity_id}",
                basis=basis,
                activity_id=a.id,
                activity_name=a.name,
                reason=reason,
                inputs_used=inputs,
                evidence_class=a.evidence_class,
                source_ids=list(a.source_ids),
                watch_for=a.watch_for,
                video_can_measure=a.video_can_measure,
                limitations=list(a.limitations),
                **kw,
            )
        )

    for finding in ctx.findings if ctx.state == "supported" else []:
        for activity_id in _usable(RULE_ACTIVITIES.get(finding.get("rule_id", ""), []), s):
            add(
                activity_id,
                "analysis_based",
                f'Your latest analysis found something worth a look: "{finding["title"]}". This practice works on the same part of the stroke. It is not a confirmed fault.',
                ["supported finding from your latest analysis", "swimming level", "equipment"],
                finding_ids=[finding["id"]],
                finding_titles=[finding["title"]],
                video_id=ctx.video_id,
                analysis_id=ctx.analysis_id,
                assumptions=[
                    "Practising it is assumed to be a reasonable response; no source in the library shows it changes this measurement."
                ],
            )
    goals = ([s.primary_goal] if s.primary_goal else []) + [
        g for g in s.goals if g != s.primary_goal
    ]
    for goal in goals:
        for activity_id in _usable(GOAL_ACTIVITIES[goal], s):
            add(
                activity_id,
                "goal_based",
                f"You chose {GOAL_LABELS[goal]} as a goal. This is general practice for that goal; it does not mean AquaTrack found a problem in your swimming.",
                ["your goals", "swimming level", "equipment"],
                goal_keys=[goal],
                assumptions=["Chosen from your goal alone, not from a measurement."],
            )
    if not recs:
        for activity_id in _usable(GENERAL_ACTIVITIES, s):
            add(
                activity_id,
                "general",
                "You have not chosen a goal yet, so this is a general freestyle practice. It does not mean AquaTrack found a problem in your swimming.",
                ["swimming level"],
                assumptions=[
                    "A conservative general choice; add goals in your profile for a plan built around them."
                ],
            )
    return recs


def _main_activity(kind: str, s: Swimmer, brisk_allowed: bool) -> str:
    difficulty = _difficulty(s)
    if kind == "easy" or difficulty == "easy":
        return "main.easy_repeats" if kind != "technique" else "main.technique_swim"
    if kind == "technique":
        return "main.technique_swim"
    options = ["main.steady_repeats"]
    if brisk_allowed and difficulty == "challenging" and "speed" in s.goals:
        options.insert(0, "main.pace_change")
    usable = _usable(options, s)
    return usable[0] if usable else "main.easy_repeats"


TITLES = {
    "technique": (
        "Technique practice",
        "Unhurried practice of one or two points, then easy swimming.",
    ),
    "steady": ("Steady swim", "A short technique reminder, then a steady block of swimming."),
    "easy": ("Easy swim", "A relaxed session with plenty of rest."),
}


def build_session(
    s: Swimmer,
    recs: list[Recommendation],
    on: date,
    kind: str = "technique",
    rotation: int = 0,
    brisk_allowed: bool = True,
) -> PlannedSession:
    total, _ = session_minutes(s)
    total = max(total, MIN_SESSION_MIN)
    warm, cool, blocks, main = _split(total, kind)
    items = [_item("warm.easy_swim", warm, s)]
    order = recs[rotation % len(recs) :] + recs[: rotation % len(recs)] if recs else []
    # A supported finding always comes first, whatever the rotation.
    order.sort(key=lambda r: r.basis != "analysis_based")
    chosen = order[: len(blocks)]
    main_id = _main_activity(kind, s, brisk_allowed)
    main_max = library.ACTIVITIES[main_id].max_minutes
    extra = sum(
        blocks[len(chosen) :]
    )  # technique time with nothing to fill it goes to the main set
    for minutes, rec in zip(blocks, chosen, strict=False):
        items.append(_item(rec.activity_id, minutes, s, rec))
    main_minutes = main + extra
    if main_minutes > 0:
        items.append(_item(main_id, min(main_minutes, main_max), s))
        if main_minutes > main_max:  # the rest becomes easy swimming rather than a longer hard set
            other = "main.technique_swim" if main_id == "main.easy_repeats" else "main.easy_repeats"
            items.append(_item(other, main_minutes - main_max, s))
    items.append(_item("cool.easy_swim", cool, s))
    if s.typical_distance_m:
        _fit_distance(items, s)
    title, objective = TITLES[kind]
    basis = (
        "analysis_based"
        if any(r.basis == "analysis_based" for r in chosen)
        else "goal_based"
        if any(r.basis == "goal_based" for r in chosen) or (s.goals and not chosen)
        else "general"
    )
    focus = ", ".join(i.name for i in items if i.recommendation_id) or "Easy freestyle"
    intensities = [i.intensity for i in items]
    safety = list(SAFETY)
    if s.age is not None and s.age < 18:
        safety.append(YOUNG_NOTE)
    return PlannedSession(
        date=on.isoformat(),
        title=title,
        objective=objective,
        level=_level(s) if s.level else "not set (planned as a beginner)",
        minutes=sum(i.minutes for i in items),
        distance_m=sum(i.distance_m or 0 for i in items) or None,
        intensity="brisk"
        if "brisk" in intensities
        else "moderate"
        if "moderate" in intensities
        else "easy",
        focus=focus,
        basis=basis,
        items=items,
        goal_keys=sorted({g for r in chosen for g in r.goal_keys}),
        finding_ids=sorted({f for r in chosen for f in r.finding_ids}),
        rest_guidance="Rest between repeats as the activities say, and longer whenever you want. Leave at least a day before your next brisk session.",
        safety=safety,
    )


def _fit_distance(items: list[PlanItem], s: Swimmer) -> None:
    """Keep the distance guide within what the swimmer usually swims, by trimming repeats
    from the longest sets first. The minutes stay: the time left over is extra rest."""
    while sum(i.distance_m or 0 for i in items) > s.typical_distance_m:
        longest = max(
            (i for i in items if i.activity_id and (i.distance_m or 0) > 0),
            key=lambda i: i.distance_m,
            default=None,
        )
        repeat = library.ACTIVITIES[longest.activity_id].repeat_m if longest else None
        if not longest or not repeat or longest.distance_m <= repeat:
            break
        longest.distance_m -= repeat
        longest.sets = f"about {longest.distance_m // repeat} x {repeat} m"


def _pick_days(start: date, days: list[str], n: int) -> list[date]:
    window = [start + timedelta(d) for d in range(7)]
    open_days = [d for d in window if not days or DAYS[d.weekday()] in days]
    n = min(n, len(open_days))
    if n <= 0:
        return []
    if n == len(open_days):
        return open_days
    return [open_days[round(i * len(open_days) / n)] for i in range(n)]  # spread out


def _checkpoint(ctx: AnalysisContext) -> SessionCheckpoint:
    if ctx.checkpoints:
        first = ctx.checkpoints[0]
        return SessionCheckpoint(
            title="Optional: film a follow-up clip",
            what_to_film=str(
                first.get("what_to_film") or "Film from the side, with your whole body in view."
            ),
            checkpoint_ids=[str(c.get("id", "")) for c in ctx.checkpoints][:4],
            source_video_id=ctx.video_id,
            note="Your latest analysis suggested this. A later clip is compared only if it was filmed the same way.",
        )
    return SessionCheckpoint(
        title="Optional: film a clip",
        what_to_film="From the side, steady camera, whole body in view, at least six stroke cycles of one arm.",
        note="Only if you would like measurements. The plan does not depend on it.",
    )


def _inputs(s: Swimmer, ctx: AnalysisContext, history: History) -> PlanInputs:
    return PlanInputs(
        level=s.level,
        sessions_per_week=s.sessions_per_week,
        session_minutes=s.session_minutes,
        days=s.days,
        difficulty=s.difficulty,
        equipment=s.equipment,
        goals=s.goals,
        primary_goal=s.primary_goal,
        typical_distance_m=s.typical_distance_m,
        video_id=ctx.video_id,
        analysis_id=ctx.analysis_id,
        feedback_id=ctx.feedback_id,
        analysis_state=ctx.state,
        completed_before=history.completed,
    )


def _common_notes(
    s: Swimmer, ctx: AnalysisContext, history: History
) -> tuple[list[str], list[str]]:
    assumptions, notes = [], []
    if s.level is None:
        assumptions.append("Your swimming level is not set, so the plan is written for a beginner.")
    if s.difficulty and _difficulty(s) != s.difficulty:
        assumptions.append(
            f"You chose {s.difficulty}; the plan uses {_difficulty(s)} as a more cautious choice for your level or age."
        )
    if s.strokes and "Freestyle" not in s.strokes:
        notes.append(
            "The activity library covers freestyle only for now; warm-up and cool-down can be any stroke you like."
        )
    if ctx.state == "supported":
        notes.append(
            "Part of this plan is linked to a supported finding in your latest analysis. It is something to look at, not a confirmed fault."
        )
    elif ctx.state == "no_supported_issue":
        notes.append(
            "Your latest analysis found no supported technique issue, so nothing in this plan is a correction."
        )
    elif ctx.state == "unavailable":
        notes.append(
            "Your latest video could not be measured, so nothing in this plan comes from it."
        )
    else:
        notes.append("No analysed video was used for this plan.")
    if history.recent_skipped > history.recent_completed and history.recent_skipped:
        notes.append(
            "You skipped more sessions than you completed in the last two weeks. The plan keeps to your settings; change them if another schedule suits you better."
        )
    if s.missing:
        notes.append(
            "Not set yet: "
            + ", ".join(s.missing)
            + ". The plan uses cautious defaults for these; you can edit everything."
        )
    return assumptions, notes


def _basis(sessions: list[PlannedSession], s: Swimmer) -> str:
    kinds = {x.basis for x in sessions}
    return "analysis_based" if "analysis_based" in kinds else "goal_based" if s.goals else "general"


def _summary(basis: str, sessions: list[PlannedSession], s: Swimmer, week: bool) -> str:
    what = {
        "analysis_based": "Partly based on a supported finding in your latest analysis; the rest follows your goals.",
        "goal_based": "Based on the goals you chose, not on a detected technique problem.",
        "general": "A conservative general plan. Add goals in your profile for a plan built around them.",
    }[basis]
    if not sessions:
        return (
            "No session could be planned on the days you have available. Check your available days."
        )
    minutes = sessions[0].minutes
    shape = (
        f"{len(sessions)} {'session' if len(sessions) == 1 else 'sessions'} of about {minutes} minutes in these 7 days"
        if week
        else f"One session of about {minutes} minutes"
    )
    return f"{shape}. {what} It is a suggestion you can edit, not a prescription."


def build_single(
    s: Swimmer, ctx: AnalysisContext, on: date, history: History | None = None
) -> TrainingPlan:
    history = history or History()
    recs = recommend(s, ctx)
    session = build_session(s, recs, on, "technique", history.completed)
    _, time_notes = session_minutes(s)
    assumptions, notes = _common_notes(s, ctx, history)
    basis = _basis([session], s)
    return TrainingPlan(
        library_version=library.LIBRARY_VERSION,
        kind="session",
        basis=basis,
        title=f"Single session: {session.title.lower()}",
        summary=_summary(basis, [session], s, False),
        start_date=on.isoformat(),
        end_date=on.isoformat(),
        sessions=[session],
        recommendations=[
            r for r in recs if any(i.recommendation_id == r.id for i in session.items)
        ],
        inputs=_inputs(s, ctx, history),
        assumptions=assumptions + time_notes,
        limitations=list(PLAN_LIMITS),
        notes=notes,
    )


def build_week(
    s: Swimmer, ctx: AnalysisContext, start: date, history: History | None = None
) -> TrainingPlan:
    """Seven days from `start`. Sessions only on the swimmer's available days, never more
    than they asked for, with at least one day without swimming."""
    history = history or History()
    recs = recommend(s, ctx)
    assumptions, notes = _common_notes(s, ctx, history)
    _, time_notes = session_minutes(s)
    wanted = s.sessions_per_week
    if wanted is None:
        wanted = DEFAULT_SESSIONS
        assumptions.append(
            f"You have not said how often you swim, so this plans {DEFAULT_SESSIONS} sessions."
        )
    limit = min(
        MAX_SESSIONS_PER_WEEK,
        BEGINNER_MAX_SESSIONS if _level(s) == "beginner" else MAX_SESSIONS_PER_WEEK,
    )
    if wanted > limit:
        assumptions.append(
            f"You asked for {wanted} sessions; the plan writes {limit} so that there are days without swimming. You can add sessions yourself."
        )
    if not s.days:
        assumptions.append(
            "You have not chosen available days, so the sessions are spread over the week."
        )
    days = _pick_days(start, s.days, min(wanted, limit))
    if s.days and len(days) < min(wanted, limit):
        notes.append(
            f"You asked for {min(wanted, limit)} sessions but only {len(days)} of your available days fall in these 7 days."
        )
    pattern = (
        ["technique", "steady", "easy"] if len(days) >= 4 else ["technique", "steady", "technique"]
    )
    sessions: list[PlannedSession] = []
    brisk_used = False
    for n, day in enumerate(days):
        kind = pattern[n % 3]
        after_hard = (
            bool(sessions)
            and sessions[-1].intensity == "brisk"
            and (day - date.fromisoformat(sessions[-1].date)).days == 1
        )
        if after_hard:
            kind = "easy"
        session = build_session(
            s, recs, day, kind, history.completed + n, brisk_allowed=not brisk_used
        )
        brisk_used = brisk_used or session.intensity == "brisk"
        if s.time_of_day:
            session.time = {"morning": "07:00", "midday": "12:00", "evening": "18:00"}[
                s.time_of_day
            ]
        sessions.append(session)
    if sessions:
        sessions[-1].checkpoint = _checkpoint(ctx)
    used = {i.recommendation_id for x in sessions for i in x.items}
    taken = {x.date for x in sessions}
    basis = _basis(sessions, s)
    return TrainingPlan(
        library_version=library.LIBRARY_VERSION,
        kind="week",
        basis=basis,
        title=f"Week from {start.isoformat()}",
        summary=_summary(basis, sessions, s, True),
        start_date=start.isoformat(),
        end_date=(start + timedelta(6)).isoformat(),
        sessions=sessions,
        rest_days=[
            RestDay(date=(start + timedelta(d)).isoformat(), guidance=REST_DAY)
            for d in range(7)
            if (start + timedelta(d)).isoformat() not in taken
        ],
        recommendations=[r for r in recs if r.id in used],
        inputs=_inputs(s, ctx, history),
        assumptions=assumptions + time_notes,
        limitations=list(PLAN_LIMITS),
        notes=notes,
    )
