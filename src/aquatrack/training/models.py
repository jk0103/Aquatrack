"""Versioned contracts for training preferences, activities, plans and sessions.

A plan is a suggestion the swimmer reviews, edits and schedules; it is never a prescription.
Every recommendation says whether it rests on the swimmer's goals or on a supported finding
from their own analysis, and the two are never mixed up.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

TRAINING_VERSION = "1.0"

Level = Literal["beginner", "hobby", "masters", "competitive"]
Intensity = Literal["easy", "moderate", "brisk"]
Category = Literal[
    "warm_up",
    "basic_freestyle",
    "rhythm_awareness",
    "body_position",
    "arm_coordination",
    "breathing",
    "endurance",
    "recovery",
    "cool_down",
    "video_checkpoint",
    "custom",
]
EvidenceClass = Literal[
    "research_supported",  # a peer-reviewed source in the library supports the practice
    "coaching_guidance",  # described by a named coaching body whose page was read
    "general_suggestion",  # a conservative, common-sense suggestion with no source behind it
    "unverified",  # not checked: never used in a plan
]
Basis = Literal["analysis_based", "goal_based", "general"]
ItemSource = Literal["recommended", "modified", "manual"]
SessionStatus = Literal["planned", "completed", "skipped", "canceled", "replaced"]

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
EQUIPMENT = ["kickboard", "pull_buoy", "fins", "snorkel"]
STROKES = ["Freestyle", "Backstroke", "Breaststroke", "Butterfly"]
TIMES_OF_DAY = ["morning", "midday", "evening"]
DIFFICULTIES = ["easy", "moderate", "challenging"]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class TrainingSource(BaseModel):
    """Where a statement about an activity comes from, and how it was checked."""

    id: str
    kind: Literal["review", "original_study", "coaching_page"]
    title: str
    authors: list[str] = []
    year: int | None = None
    publisher: str  # journal, or the organisation behind a coaching page
    doi: str = ""
    url: str
    verified_on: str
    verified_via: str
    read: Literal["abstract", "page"]
    says: str  # what we take from it, in our own words and no more
    limits: str  # how far it is from what the plan does


class Activity(BaseModel):
    id: str  # stable
    name: str
    category: Category
    stroke: str = "Freestyle"
    levels: list[Level]
    purpose: str
    instructions: list[str]
    min_minutes: int
    max_minutes: int
    repeat_m: int | None = None  # the repeat the set is written in, when it has one
    intensity: Intensity
    rest: str = ""
    equipment: list[str] = []  # needed to do it
    goals: list[str] = []  # goal keys it can serve
    metric_keys: list[str] = []  # AquaTrack metrics it relates to, if any
    rule_ids: list[str] = []  # supported interpretation rules it may be linked to
    watch_for: str = ""  # what the swimmer can notice while doing it
    video_can_measure: str = ""  # what a later video may be able to measure
    safety: list[str] = []
    evidence_class: EvidenceClass
    source_ids: list[str] = []
    limitations: list[str] = []
    active: bool = True


class Swimmer(BaseModel):
    """What the planner knows about the swimmer: the profile's own answers, nothing inferred."""

    level: Level | None = None
    age: int | None = None
    sessions_per_week: int | None = None
    session_minutes: int | None = None
    days: list[str] = []
    time_of_day: str = ""
    typical_distance_m: int | None = None
    strokes: list[str] = []
    equipment: list[str] = []
    difficulty: str = ""
    goals: list[str] = []
    primary_goal: str | None = None
    missing: list[str] = []  # preferences the swimmer has not given yet


class Recommendation(BaseModel):
    id: str
    basis: Basis
    activity_id: str
    activity_name: str
    reason: str
    inputs_used: list[str] = []
    goal_keys: list[str] = []
    finding_ids: list[str] = []
    finding_titles: list[str] = []
    video_id: str = ""
    analysis_id: str = ""
    evidence_class: EvidenceClass
    source_ids: list[str] = []
    watch_for: str = ""
    video_can_measure: str = ""
    assumptions: list[str] = []
    limitations: list[str] = []


class PlanItem(BaseModel):
    activity_id: str = ""  # empty for an activity the swimmer typed in
    name: str
    category: Category
    minutes: int
    distance_m: int | None = None
    sets: str = ""  # e.g. "about 6 x 50 m"; a guide, the time is what counts
    intensity: str = ""
    rest: str = ""
    instructions: list[str] = []
    equipment: list[str] = []
    safety: list[str] = []
    source: ItemSource = "recommended"
    recommendation_id: str = ""
    basis: Basis | None = None
    evidence_class: EvidenceClass | None = None
    done: bool = False  # ticked by the swimmer when completing the session


class SessionCheckpoint(BaseModel):
    """An optional reminder to film a clip. Never required, never counted as swimming."""

    title: str
    what_to_film: str
    checkpoint_ids: list[str] = []
    source_video_id: str = ""  # cleared if that video is deleted
    note: str = ""


class Completion(BaseModel):
    completed_on: str  # the swimmer's local date
    note: str = ""  # the swimmer's own words: shown back to them, never analysed or sent on
    recorded_at: str = Field(default_factory=_now)


class PlannedSession(BaseModel):
    id: str = ""
    plan_id: str = ""  # empty for a session the swimmer created
    plan_version: int = 0
    # Changes by one on every stored change. An edit must name the revision it was made
    # from; if the stored one has moved on, the edit is refused instead of overwriting.
    revision: int = 0
    date: str  # local calendar date, YYYY-MM-DD; no time zone conversion is ever applied
    # The day the plan first put this session on. Never changes when the swimmer moves the
    # session, so a regenerated plan knows that slot is already taken.
    planned_date: str = ""
    time: str = ""  # optional local time, HH:MM
    title: str
    objective: str = ""
    level: str = ""
    minutes: int = 0  # always the sum of the items
    distance_m: int | None = None
    intensity: str = ""
    focus: str = ""
    basis: Basis | None = None  # None for a session the swimmer created
    items: list[PlanItem] = []
    goal_keys: list[str] = []
    finding_ids: list[str] = []
    checkpoint: SessionCheckpoint | None = None
    rest_guidance: str = ""
    safety: list[str] = []
    status: SessionStatus = "planned"
    origin: Literal["generated", "manual"] = "generated"
    edited: bool = False
    completion: Completion | None = None
    linked_video_id: str = ""
    linked_video_removed: bool = False
    explained: str = ""  # optional reworded summary, validated
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class RestDay(BaseModel):
    date: str
    guidance: str


class PlanInputs(BaseModel):
    """What the planner used. Kept with the plan so it can be explained later."""

    level: str | None = None
    sessions_per_week: int | None = None
    session_minutes: int | None = None
    days: list[str] = []
    difficulty: str = ""
    equipment: list[str] = []
    goals: list[str] = []
    primary_goal: str | None = None
    typical_distance_m: int | None = None
    video_id: str = ""
    analysis_id: str = ""
    feedback_id: str = ""
    analysis_state: str = "none"  # none | unavailable | no_supported_issue | supported
    analysis_removed: bool = False  # the video behind an analysis-based plan was deleted
    completed_before: int = 0


class PlanExplanation(BaseModel):
    source: Literal["template", "llm"] = "template"
    model: str = ""
    note: str = ""


class TrainingPlan(BaseModel):
    training_version: str = TRAINING_VERSION
    library_version: str = ""
    id: str = ""
    series_id: str = ""  # the same for every version of a plan for the same dates
    version: int = 1
    kind: Literal["session", "week"]
    basis: Basis
    title: str
    summary: str  # deterministic; always present
    explained: str = ""  # optional reworded summary, validated
    explanation: PlanExplanation = PlanExplanation()
    start_date: str
    end_date: str
    status: Literal["preview", "active", "replaced"] = "preview"
    replaced_by: str = ""
    sessions: list[PlannedSession] = []
    rest_days: list[RestDay] = []
    recommendations: list[Recommendation] = []
    inputs: PlanInputs = PlanInputs()
    assumptions: list[str] = []
    limitations: list[str] = []
    notes: list[str] = []
    # Preview only: what the swimmer's schedule looked like when the preview was made.
    # Saving needs it back, and is refused if the schedule has changed since.
    token: str = ""
    created_at: str = Field(default_factory=_now)
