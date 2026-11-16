"""Training: the activity library, the deterministic planner, plan storage and edits, the
calendar, and what happens to training data when a video is deleted.

Every swimmer, profile, finding and history here is a labelled synthetic fixture. Passing
tests show the software does what it says; they are not evidence that any plan improves
anyone's swimming."""
# ruff: noqa: E501  (long fixture lines are kept whole)

import re
from datetime import date, timedelta

import pytest

from aquatrack.api import jobs, training
from aquatrack.api.store import MemoryStore
from aquatrack.api.training import TrainingError
from aquatrack.training import library, planner
from aquatrack.training.planner import AnalysisContext, History, swimmer_from_profile

UID, OTHER = "swimmer-1", "swimmer-2"
MON = date(2026, 11, 16)  # a Monday


def profile(**kw):
    """SYNTHETIC profile. `training` holds the optional preferences."""
    base = {
        "swim_level": "hobby",
        "age": 30,
        "sessions_per_week": 3,
        "minutes_per_day": 45,
        "goals": ["stroke_consistency"],
        "primary_goal": "stroke_consistency",
        "training": {"days": ["mon", "wed", "sat"], "difficulty": "moderate", "equipment": []},
    }
    training_prefs = {**base["training"], **kw.pop("training", {})}
    return {**base, **kw, "training": training_prefs}


SUPPORTED = AnalysisContext(
    state="supported",
    video_id="vid-a",
    analysis_id="a1",
    feedback_id="f1",
    findings=[
        {
            "id": "issue.timing.uneven_rhythm",
            "rule_id": "timing.uneven_rhythm",
            "title": "Stroke rhythm varies",
        }
    ],
    checkpoints=[
        {"id": "cp.recurs.x", "title": "Film again", "what_to_film": "Side view, 8 cycles."}
    ],
)
NO_ISSUE = AnalysisContext(state="no_supported_issue", video_id="vid-a", analysis_id="a1")


def week(p=None, ctx=None, start=MON, history=None):
    return planner.build_week(
        swimmer_from_profile(p or profile()), ctx or AnalysisContext(), start, history
    )


def all_text(plan) -> str:
    return " ".join(
        [plan.summary, *plan.notes, *plan.assumptions]
        + [r.reason for r in plan.recommendations]
        + [t for s in plan.sessions for i in s.items for t in [i.name, *i.instructions]]
    )


# ---------- the library ----------


def test_every_activity_is_documented_and_only_checked_ones_are_active():
    for a in library.ACTIVITIES.values():
        assert a.purpose and a.instructions and a.limitations and a.levels
        assert a.min_minutes <= a.max_minutes
        assert all(s in library.SOURCES for s in a.source_ids)
        if a.evidence_class in ("research_supported", "coaching_guidance"):
            kinds = {library.SOURCES[s].kind for s in a.source_ids}
            wanted = "coaching_page" if a.evidence_class == "coaching_guidance" else "review"
            assert wanted in kinds, a.id
        if a.active:
            assert a.safety and a.evidence_class != "unverified"
    unverified = [a for a in library.ACTIVITIES.values() if a.evidence_class == "unverified"]
    assert unverified and not any(a.active for a in unverified)
    assert all(a.id != "tech.fingertip_drag" for a in library.active())


def test_sources_say_how_they_were_checked_and_research_was_read_as_abstracts_only():
    for s in library.SOURCES.values():
        assert (
            s.verified_on
            and s.verified_via
            and s.says
            and s.limits
            and s.url.startswith("https://")
        )
        if s.kind != "coaching_page":
            assert s.doi and s.read == "abstract"


def test_nothing_in_the_library_asks_for_breath_holding_or_all_out_effort():
    risky = re.compile(
        r"hold your breath for|as long as you can|hypoxic|all-out effort|to exhaustion|fewer breaths",
        re.I,
    )
    for a in library.active():
        text = " ".join([a.purpose, *a.instructions])
        assert not risky.search(text), a.id
        assert any("Never hold your breath" in s for s in a.safety)
    assert all(a.intensity != "brisk" or "beginner" not in a.levels for a in library.active())


def test_mapped_rules_exist_in_the_interpretation_engine_and_are_never_arm_or_pending_rules():
    from aquatrack.analysis import interpretation

    source = open(interpretation.__file__).read()
    for rule in planner.RULE_ACTIVITIES:
        assert f'"{rule}"' in source and not rule.startswith("pending.")
    for ids in list(planner.RULE_ACTIVITIES.values()) + list(planner.GOAL_ACTIVITIES.values()):
        assert all(library.ACTIVITIES[i].active for i in ids)
    assert set(planner.GOAL_ACTIVITIES) == set(interpretation.GOALS)


# ---------- recommendations ----------


def test_without_a_supported_issue_the_plan_is_goal_based_and_claims_no_problem():
    for ctx in (AnalysisContext(), NO_ISSUE, AnalysisContext(state="unavailable", video_id="v")):
        plan = week(ctx=ctx)
        assert plan.basis == "goal_based" and plan.sessions
        assert all(r.basis == "goal_based" and not r.finding_ids for r in plan.recommendations)
        assert all(s.basis == "goal_based" and not s.finding_ids for s in plan.sessions)
        text = all_text(plan)
        assert "not on a detected technique problem" in plan.summary
        assert not re.search(
            r"your (stroke|rhythm) (is|was) (uneven|inconsistent)|we (found|measured)", text, re.I
        )
    assert "no supported technique issue" in " ".join(week(ctx=NO_ISSUE).notes)
    assert "could not be measured" in " ".join(week(ctx=AnalysisContext(state="unavailable")).notes)


def test_a_supported_finding_links_practice_to_the_analysis_and_says_it_is_not_a_fault():
    plan = week(ctx=SUPPORTED)
    assert plan.basis == "analysis_based"
    linked = [r for r in plan.recommendations if r.basis == "analysis_based"]
    assert linked and all(r.finding_ids == ["issue.timing.uneven_rhythm"] for r in linked)
    assert all(r.video_id == "vid-a" and r.analysis_id == "a1" for r in linked)
    assert all(
        "not a confirmed fault" in r.reason and r.assumptions and r.limitations for r in linked
    )
    assert all(r.watch_for and r.video_can_measure for r in linked)
    assert plan.sessions[0].items[1].basis == "analysis_based"  # it comes first after the warm-up
    assert plan.sessions[-1].checkpoint.checkpoint_ids == ["cp.recurs.x"]
    assert plan.sessions[-1].checkpoint.source_video_id == "vid-a"


def test_a_finding_whose_rule_has_no_mapped_practice_changes_nothing():
    ctx = AnalysisContext(
        state="supported", findings=[{"id": "f", "rule_id": "pending.low_elbow", "title": "Elbow"}]
    )
    plan = week(ctx=ctx)
    assert plan.basis == "goal_based" and not any(r.finding_ids for r in plan.recommendations)


def test_no_goals_gives_a_general_plan_that_says_so():
    plan = week(profile(goals=[], primary_goal=None))
    assert plan.basis == "general" and "conservative general plan" in plan.summary
    assert all(r.basis == "general" for r in plan.recommendations)


def test_missing_preferences_are_listed_and_planned_with_cautious_defaults():
    s = swimmer_from_profile(None)
    assert set(s.missing) >= {
        "swimming level",
        "sessions per week",
        "time per session",
        "available days",
        "goals",
    }
    plan = planner.build_week(s, AnalysisContext(), MON)
    assert len(plan.sessions) == planner.DEFAULT_SESSIONS
    assert all(
        x.minutes == planner.DEFAULT_SESSION_MIN and x.intensity == "easy" for x in plan.sessions
    )
    assert any("written for a beginner" in a for a in plan.assumptions)
    assert any("Not set yet" in n for n in plan.notes)


def test_a_personal_best_never_raises_the_assumed_level():
    fast = {"pbs": [{"event": "100 Free", "pool": "50 m", "seconds": 50.0}], "minutes_per_day": 60}
    s = swimmer_from_profile(fast)
    assert s.level is None
    plan = planner.build_single(s, AnalysisContext(), MON)
    assert plan.sessions[0].intensity == "easy" and plan.sessions[0].minutes <= 45


@pytest.mark.parametrize(
    "level,difficulty,expect",
    [
        ("beginner", "challenging", "easy moderate"),
        ("hobby", "challenging", "easy moderate"),
        ("competitive", "challenging", "brisk"),
    ],
)
def test_level_limits_how_hard_a_plan_can_be(level, difficulty, expect):
    p = profile(
        swim_level=level,
        goals=["speed"],
        primary_goal="speed",
        minutes_per_day=60,
        training={"difficulty": difficulty},
    )
    plan = week(p)
    hardest = max(plan.sessions, key=lambda s: ["easy", "moderate", "brisk"].index(s.intensity))
    assert hardest.intensity in expect.split()
    brisk = [s for s in plan.sessions if s.intensity == "brisk"]
    assert len(brisk) <= 1  # never more than one brisk session in a week
    if level == "beginner":
        ids = {i.activity_id for s in plan.sessions for i in s.items}
        assert "main.steady_repeats" not in ids and "main.pace_change" not in ids


def test_younger_swimmers_get_general_easy_to_moderate_plans_with_a_supervision_note():
    teen = week(
        profile(
            age=15,
            swim_level="competitive",
            minutes_per_day=120,
            goals=["speed"],
            primary_goal="speed",
            training={"difficulty": "challenging"},
        )
    )
    assert all(s.intensity != "brisk" and s.minutes <= 60 for s in teen.sessions)
    assert all(any("younger swimmer" in x for x in s.safety) for s in teen.sessions)
    child = week(profile(age=10, minutes_per_day=90))
    assert all(s.intensity == "easy" and s.minutes <= 45 for s in child.sessions)


def test_equipment_and_level_decide_which_activities_can_be_offered():
    p = profile(goals=["breathing"], primary_goal="breathing")
    without = {i.activity_id for s in week(p).sessions for i in s.items}
    assert "tech.kickboard_breathing" not in without and "tech.breathe_every_three" in without
    p["training"]["equipment"] = ["kickboard"]
    assert "tech.kickboard_breathing" in {i.activity_id for s in week(p).sessions for i in s.items}
    board = library.ACTIVITIES["tech.kickboard_breathing"]
    assert "kickboard" in library.eligible(board, "hobby", [])
    assert library.eligible(library.ACTIVITIES["main.pace_change"], "beginner", []) is not None


# ---------- sessions ----------


@pytest.mark.parametrize("minutes", [15, 20, 25, 30, 40, 45, 60])
def test_a_session_always_fits_the_time_the_swimmer_has(minutes):
    plan = planner.build_single(
        swimmer_from_profile(profile(minutes_per_day=minutes)), AnalysisContext(), MON
    )
    s = plan.sessions[0]
    assert s.minutes == sum(i.minutes for i in s.items) == minutes
    assert s.items[0].category == "warm_up" and s.items[-1].category == "cool_down"
    assert all(
        library.ACTIVITIES[i.activity_id].min_minutes
        <= i.minutes
        <= library.ACTIVITIES[i.activity_id].max_minutes
        for i in s.items
    )
    assert s.title and s.objective and s.safety and s.rest_guidance and s.level


def test_more_time_than_the_level_cap_is_not_filled_and_the_plan_says_so():
    plan = week(profile(minutes_per_day=180))
    assert all(s.minutes == planner.SESSION_CAP["hobby"] for s in plan.sessions)
    assert any("conservative choice" in a for a in plan.assumptions)


def test_the_distance_guide_stays_within_what_the_swimmer_usually_swims():
    free = week(profile(minutes_per_day=60)).sessions[0]
    capped = week(profile(minutes_per_day=60, training={"typical_distance_m": 800})).sessions[0]
    assert free.distance_m > 800 >= capped.distance_m and capped.minutes == free.minutes


def test_the_same_inputs_always_give_the_same_plan():
    def content(plan):
        return plan.model_dump(
            exclude={"created_at": True, "sessions": {"__all__": {"created_at", "updated_at"}}}
        )

    assert content(week(ctx=SUPPORTED)) == content(week(ctx=SUPPORTED))


def test_nothing_promises_results_and_every_plan_carries_its_limits():
    for plan in (week(), week(ctx=SUPPORTED), week(profile(goals=["speed"], primary_goal="speed"))):
        assert not re.search(
            r"will (improve|make you|get you)|guarantee|faster times in", all_text(plan), re.I
        )
        assert any("No source in the library shows" in x for x in plan.limitations)
        assert "suggestion you can edit, not a prescription" in plan.summary


# ---------- weeks ----------


@pytest.mark.parametrize(
    "days,wanted,expect",
    [
        (["sat"], 1, ["2026-11-21"]),
        (["mon", "wed", "sat"], 3, ["2026-11-16", "2026-11-18", "2026-11-21"]),
        (["tue", "thu"], 4, ["2026-11-17", "2026-11-19"]),  # never on a day that is not available
        ([], 2, None),
    ],
)
def test_sessions_fall_only_on_available_days_and_never_exceed_the_frequency(days, wanted, expect):
    plan = week(profile(sessions_per_week=wanted, training={"days": days}))
    dates = [s.date for s in plan.sessions]
    assert len(dates) <= wanted
    if expect:
        assert dates == expect
    else:
        assert len(dates) == 2 and any("spread over the week" in a for a in plan.assumptions)
    assert {r.date for r in plan.rest_days}.isdisjoint(dates)
    assert len(plan.rest_days) + len(dates) == 7 and all(r.guidance for r in plan.rest_days)
    if days == ["tue", "thu"]:
        assert any("only 2 of your available days" in n for n in plan.notes)


def test_a_week_started_mid_week_never_schedules_in_the_past():
    plan = week(start=date(2026, 11, 19))  # a Thursday
    assert plan.start_date == "2026-11-19" and plan.end_date == "2026-11-25"
    assert all("2026-11-19" <= s.date <= "2026-11-25" for s in plan.sessions)


def test_there_is_always_a_day_without_swimming_and_beginners_are_capped():
    many = week(profile(swim_level="competitive", sessions_per_week=10, training={"days": []}))
    assert len(many.sessions) == planner.MAX_SESSIONS_PER_WEEK and many.rest_days
    assert any("days without swimming" in a for a in many.assumptions)
    beginner = week(profile(swim_level="beginner", sessions_per_week=7, training={"days": []}))
    assert len(beginner.sessions) == planner.BEGINNER_MAX_SESSIONS


def test_history_rotates_the_practice_but_never_raises_the_load():
    first = week(history=History(completed=0))
    later = week(history=History(completed=5, recent_completed=5))
    assert [s.minutes for s in first.sessions] == [s.minutes for s in later.sessions]
    assert len(first.sessions) == len(later.sessions)
    order = lambda p: [i.activity_id for i in p.sessions[0].items if i.recommendation_id]  # noqa: E731
    assert order(first) != order(later)
    skipped = week(history=History(recent_skipped=3, recent_completed=1))
    assert len(skipped.sessions) == len(first.sessions)
    assert any("skipped more sessions" in n for n in skipped.notes)


# ---------- storage, edits, calendar (service level, in-memory store) ----------


@pytest.fixture
def store():
    s = MemoryStore()
    s.profiles[UID] = profile(training={"equipment": ["kickboard"]})
    s.profiles[OTHER] = profile()
    return s


def saved_week(store, uid=UID, start=MON, **kw):
    out = training.save_plan(store, uid, "week", start, **kw)
    assert out["saved"], out
    return out["plan"]


def stored(store, session_id):
    return store.get_doc("training_sessions", session_id)


def test_a_preview_stores_nothing_and_saving_stores_the_plan_and_its_sessions(store):
    preview = training.generate(store, UID, "week", MON)
    assert preview.status == "preview" and not store.docs["training_plans"]
    plan = saved_week(store)
    assert plan["status"] == "active" and plan["version"] == 1 and len(plan["sessions"]) == 3
    assert all(stored(store, s["id"])["uid"] == UID for s in plan["sessions"])
    assert all(s["status"] == "planned" and s["completion"] is None for s in plan["sessions"])
    over = training.overview(store, UID, MON)
    assert over["week"] == {
        "start": "2026-11-16",
        "end": "2026-11-22",
        "planned": 3,
        "completed": 0,
        "skipped": 0,
        "canceled": 0,
    }
    assert [s["date"] for s in over["upcoming"]] == ["2026-11-16", "2026-11-18", "2026-11-21"]
    assert over["plans"][0]["id"] == plan["id"] and over["llm_enabled"] is False


def test_regenerating_never_silently_overwrites_and_keeps_edits_and_history(store):
    first = saved_week(store)
    a, b, c = (s["id"] for s in first["sessions"])
    training.update_session(store, UID, a, {"time": "06:30"})  # edited by the swimmer
    training.complete_session(store, UID, b, {"completed_on": "2026-11-18"})
    again = training.save_plan(store, UID, "week", MON)
    assert again["saved"] is False and again["conflict"]["kind"] == "week_overlap"
    assert again["conflict"]["plans"][0] == {
        "id": first["id"],
        "title": first["title"],
        "version": 1,
        "edited": 1,
        "unedited": 1,
        "recorded": 1,
    }
    assert len(store.docs["training_plans"]) == 1  # nothing was stored by the refused save
    second = saved_week(store, confirm=True)
    assert second["version"] == 2 and second["series_id"] == first["series_id"]
    old = store.get_doc("training_plans", first["id"])
    assert old["status"] == "replaced" and old["replaced_by"] == second["id"]
    # the swimmer's own sessions keep their ids and move over to the new version
    assert stored(store, a)["status"] == "planned" and stored(store, a)["time"] == "06:30"
    assert stored(store, b)["status"] == "completed"
    assert stored(store, a)["plan_id"] == stored(store, b)["plan_id"] == second["id"]
    assert stored(store, a)["plan_version"] == 1  # where it came from is still recorded
    assert stored(store, c)["status"] == "replaced"  # kept in storage with the old version
    assert [s["id"] for s in second["sessions"]][:2] == [a, b]
    assert [s["date"] for s in second["sessions"]] == ["2026-11-16", "2026-11-18", "2026-11-21"]
    assert sum("Kept the session you already had" in n for n in second["notes"]) == 2
    days = [s["date"] for s in training.calendar(store, UID, MON, MON + timedelta(6))["sessions"]]
    assert days == ["2026-11-16", "2026-11-18", "2026-11-21"]  # no duplicates on any day


def test_a_moved_session_keeps_its_slot_so_regenerating_adds_no_duplicate(store):
    """The Phase 6 defect: move Monday's session to Tuesday, regenerate, and Monday got a
    second session. The slot the plan first gave a session now stays taken."""
    first = saved_week(store)
    monday = first["sessions"][0]
    moved = training.update_session(store, UID, monday["id"], {"date": "2026-11-17"})
    assert (moved["planned_date"], moved["date"]) == ("2026-11-16", "2026-11-17")
    asked = training.save_plan(store, UID, "week", MON)
    assert asked["conflict"]["moved"] == [
        {
            "id": monday["id"],
            "title": monday["title"],
            "planned_date": "2026-11-16",
            "date": "2026-11-17",
        }
    ]
    second = saved_week(store, confirm=True)
    cal = training.calendar(store, UID, MON, MON + timedelta(6))
    assert [s["date"] for s in cal["sessions"]] == ["2026-11-17", "2026-11-18", "2026-11-21"]
    assert len(cal["sessions"]) == 3  # still three sessions this week, not four
    assert cal["sessions"][0]["id"] == monday["id"]  # the same session, not a copy
    assert any("moved to 2026-11-17 and is kept" in n for n in second["notes"])
    assert "2026-11-17" not in {r["date"] for r in cal["rest_days"]}
    # and again: regenerating twice still adds nothing
    saved_week(store, confirm=True)
    assert len(training.calendar(store, UID, MON, MON + timedelta(6))["sessions"]) == 3


def test_a_cancelled_session_frees_its_day_and_a_skipped_one_does_not(store):
    a, b, c = (s["id"] for s in saved_week(store)["sessions"])
    training.update_session(store, UID, a, {"status": "canceled"})
    training.update_session(store, UID, b, {"status": "skipped"})
    saved_week(store, confirm=True)
    by_day = {}
    for s in training.calendar(store, UID, MON, MON + timedelta(6))["sessions"]:
        by_day.setdefault(s["date"], []).append(s["status"])
    assert sorted(by_day["2026-11-16"]) == ["canceled", "planned"]  # a new one may take the day
    assert by_day["2026-11-18"] == ["skipped"]  # the record of the skipped day stands alone
    assert by_day["2026-11-21"] == ["planned"]
    assert stored(store, a)["status"] == "canceled" and stored(store, b)["status"] == "skipped"


def test_an_edit_made_from_an_old_copy_is_refused_instead_of_overwriting(store):
    """Two tabs: both opened the session at revision 1; the first saves, the second must
    not silently win."""
    session = saved_week(store)["sessions"][0]
    assert session["revision"] == 1
    tab_one = training.update_session(store, UID, session["id"], {"revision": 1, "time": "06:30"})
    assert tab_one["revision"] == 2
    for stale in (
        lambda: training.update_session(
            store, UID, session["id"], {"revision": 1, "time": "20:00"}
        ),
        lambda: training.complete_session(
            store, UID, session["id"], {"revision": 1, "completed_on": "2026-11-16"}
        ),
        lambda: training.delete_session(store, UID, session["id"], revision=1),
    ):
        with pytest.raises(TrainingError) as e:
            stale()
        assert e.value.status_code == 409 and "changed somewhere else" in e.value.detail
    now = stored(store, session["id"])
    assert (now["time"], now["status"], now["revision"]) == ("06:30", "planned", 2)
    done = training.complete_session(
        store, UID, session["id"], {"revision": 2, "completed_on": "2026-11-16"}
    )
    assert done["revision"] == 3
    with pytest.raises(
        TrainingError, match="changed somewhere else"
    ):  # a completion is protected too
        training.update_session(store, UID, session["id"], {"revision": 2, "status": "skipped"})
    assert stored(store, session["id"])["status"] == "completed"


def test_a_write_that_races_another_is_caught_by_the_store_itself(store, monkeypatch):
    """Even when both requests read the same revision before either writes, only one
    write lands: the compare-and-set is inside the store."""
    session = saved_week(store)["sessions"][0]
    real = training._own_session

    def read_then_someone_else_writes(st, uid, sid):
        mine = real(st, uid, sid)
        other = real(st, uid, sid)
        other.title = "Changed in the other tab"
        monkeypatch.setattr(training, "_own_session", real)
        training._save_session(st, uid, other)
        return mine

    monkeypatch.setattr(training, "_own_session", read_then_someone_else_writes)
    with pytest.raises(TrainingError, match="changed somewhere else"):
        training.update_session(store, UID, session["id"], {"title": "Mine"})
    assert stored(store, session["id"])["title"] == "Changed in the other tab"


def test_a_plan_is_not_saved_from_a_preview_the_schedule_has_moved_on_from(store):
    first = saved_week(store)
    preview = training.generate(store, UID, "week", MON)
    assert preview.token and training.generate(store, UID, "week", MON).token == preview.token
    training.update_session(store, UID, first["sessions"][0]["id"], {"date": "2026-11-17"})
    before = {k: dict(v) for k, v in store.docs.items()}
    with pytest.raises(TrainingError) as e:
        training.save_plan(store, UID, "week", MON, confirm=True, token=preview.token)
    assert e.value.status_code == 409 and "Preview the plan again" in e.value.detail
    assert store.docs == before  # nothing was written
    fresh = training.generate(store, UID, "week", MON).token
    assert fresh != preview.token
    assert training.save_plan(store, UID, "week", MON, confirm=True, token=fresh)["saved"]


def test_two_plan_saves_at_the_same_moment_cannot_both_land(store, monkeypatch):
    real = training._sessions

    def another_save_gets_in_first(st, uid):
        monkeypatch.setattr(training, "_sessions", real)
        state = st.get_doc("training_state", uid) or {}
        st.set_doc(
            "training_state",
            uid,
            {"uid": uid, "id": uid, "revision": int(state.get("revision", 0)) + 1},
        )
        return real(st, uid)

    saved_week(store)  # creates the state document
    monkeypatch.setattr(training, "_lock_schedule", training._lock_schedule)
    original = store.get_doc

    def stale_state(collection, doc_id):
        doc = original(collection, doc_id)
        if collection == "training_state" and doc:
            store.docs["training_state"][doc_id]["revision"] += 1  # the other save wins the race
        return doc

    monkeypatch.setattr(store, "get_doc", stale_state)
    with pytest.raises(TrainingError, match="Preview the plan again"):
        training.save_plan(store, UID, "week", MON + timedelta(7))
    monkeypatch.setattr(store, "get_doc", original)
    assert len(store.docs["training_plans"]) == 1


def test_edits_are_replaced_only_when_the_swimmer_says_so(store):
    first = saved_week(store)
    a = first["sessions"][0]["id"]
    training.update_session(store, UID, a, {"time": "06:30"})
    second = saved_week(store, confirm=True, discard_edits=True)
    assert stored(store, a)["status"] == "replaced" and len(second["sessions"]) == 3
    assert a not in [s["id"] for s in second["sessions"]]


def test_a_changed_preference_changes_the_next_plan_not_the_stored_one(store):
    first = saved_week(store)
    store.profiles[UID]["sessions_per_week"] = 1
    store.profiles[UID]["training"]["days"] = ["sun"]
    assert len(training.overview(store, UID, MON)["plans"][0]["sessions"]) == 3
    assert [s.date for s in training.generate(store, UID, "week", MON).sessions] == ["2026-11-22"]
    assert first["inputs"]["sessions_per_week"] == 3  # the plan remembers what it was built from


def test_a_single_session_on_a_day_that_has_one_asks_first(store):
    one = training.save_plan(store, UID, "session", MON)
    assert one["saved"] and one["plan"]["kind"] == "session" and len(one["plan"]["sessions"]) == 1
    two = training.save_plan(store, UID, "session", MON)
    assert two["saved"] is False and two["conflict"]["kind"] == "date_has_session"
    assert training.save_plan(store, UID, "session", MON, confirm=True)["saved"]


def test_sessions_shorter_than_the_minimum_are_refused_with_a_reason(store):
    store.profiles[UID]["minutes_per_day"] = 10
    with pytest.raises(TrainingError, match="at least 15 minutes"):
        training.generate(store, UID, "session", MON)
    with pytest.raises(TrainingError, match="single session or a weekly plan"):
        training.generate(store, UID, "month", MON)


def items_of(session):
    return [
        {"activity_id": i["activity_id"], "name": i["name"], "minutes": i["minutes"]}
        for i in session["items"]
    ]


def test_editing_records_what_was_recommended_modified_or_added_by_the_swimmer(store):
    session = saved_week(store)["sessions"][0]
    items = items_of(session)
    items[1]["minutes"] = 5  # change a recommended activity
    del items[2]  # remove one
    items.insert(
        2, {"activity_id": "tech.kickboard_breathing", "minutes": 5}
    )  # add from the library
    items.append({"activity_id": "", "name": "Backstroke for fun", "minutes": 4})  # own activity
    out = training.update_session(
        store, UID, session["id"], {"items": items, "title": "My Monday swim"}
    )
    by = {i["name"]: i for i in out["items"]}
    assert by["Easy warm-up swim"]["source"] == "recommended"
    assert (
        by[items[1]["name"]]["source"] == "modified" and by[items[1]["name"]]["recommendation_id"]
    )
    assert (
        by["Kickboard breathing"]["source"] == "manual"
        and not by["Kickboard breathing"]["recommendation_id"]
    )
    assert by["Backstroke for fun"] == {
        **by["Backstroke for fun"],
        "source": "manual",
        "category": "custom",
        "activity_id": "",
        "instructions": [],
    }
    assert out["edited"] and out["title"] == "My Monday swim"
    assert out["minutes"] == sum(i["minutes"] for i in out["items"])


@pytest.mark.parametrize(
    "change,message",
    [
        ({"items": []}, "at least one activity"),
        ({"items": [{"activity_id": "nope", "minutes": 5}]}, "not in the library"),
        ({"items": [{"activity_id": "tech.fingertip_drag", "minutes": 5}]}, "not available"),
        ({"items": [{"activity_id": "warm.easy_swim", "minutes": 300}]}, "between 5 and 15"),
        ({"items": [{"activity_id": "warm.easy_swim", "minutes": 5.5}]}, "whole number"),
        (
            {"items": [{"activity_id": "main.pace_change", "minutes": 10}]},
            "not offered at your swimming level",
        ),
        ({"items": [{"activity_id": "tech.side_kick", "minutes": 5}] * 2}, "listed twice"),
        ({"items": [{"activity_id": "", "name": "", "minutes": 5}]}, "Name your own activity"),
        (
            {
                "items": [
                    {"activity_id": "", "name": "Long swim", "minutes": 120},
                    {"activity_id": "", "name": "More", "minutes": 100},
                ]
            },
            "under 180",
        ),
        ({"date": "2026-02-30"}, "not a real calendar date"),
        ({"date": "2026-11-6"}, "YYYY-MM-DD"),
        ({"time": "25:00"}, "HH:MM"),
        ({"title": ""}, "title"),
        ({"status": "completed"}, "planned, skipped or cancelled"),
    ],
)
def test_impossible_edits_are_refused_and_change_nothing(store, change, message):
    session = saved_week(store)["sessions"][0]
    before = stored(store, session["id"])
    with pytest.raises(TrainingError, match=message):
        training.update_session(store, UID, session["id"], change)
    assert stored(store, session["id"]) == before


def test_a_brisk_set_needs_a_warm_up_and_cannot_be_doubled(store):
    store.profiles[UID].update(swim_level="masters")
    session = saved_week(store)["sessions"][0]
    with pytest.raises(TrainingError, match="needs a warm-up"):
        training.update_session(
            store,
            UID,
            session["id"],
            {"items": [{"activity_id": "main.pace_change", "minutes": 10}]},
        )
    ok = [
        {"activity_id": "warm.easy_swim", "minutes": 10},
        {"activity_id": "main.pace_change", "minutes": 10},
    ]
    assert training.update_session(store, UID, session["id"], {"items": ok})["intensity"] == "brisk"


def test_needed_equipment_is_checked_against_what_the_swimmer_has(store):
    store.profiles[UID]["training"]["equipment"] = []
    session = saved_week(store)["sessions"][0]
    items = items_of(session) + [{"activity_id": "tech.kickboard_breathing", "minutes": 5}]
    with pytest.raises(TrainingError, match="needs a kickboard"):
        training.update_session(store, UID, session["id"], {"items": items})


def test_rescheduling_keeps_the_local_date_and_time_exactly_as_typed(store):
    session = saved_week(store)["sessions"][0]
    out = training.update_session(
        store, UID, session["id"], {"date": "2026-11-17", "time": "23:30"}
    )
    assert (out["date"], out["time"], out["edited"]) == ("2026-11-17", "23:30", True)
    cal = training.calendar(store, UID, date(2026, 11, 17), date(2026, 11, 17))
    assert [s["id"] for s in cal["sessions"]] == [session["id"]]
    # the day it moved to is no longer shown as a rest day; the day it left has no session
    week_view = training.calendar(store, UID, MON, MON + timedelta(6))
    assert "2026-11-17" not in {r["date"] for r in week_view["rest_days"]}
    assert "2026-11-16" not in {s["date"] for s in week_view["sessions"]}


def test_a_session_is_completed_only_when_the_swimmer_says_so(store):
    session = saved_week(store, start=date(2020, 1, 6))["sessions"][0]  # long in the past
    assert training.overview(store, UID, MON)["totals"] == {"completed": 0, "skipped": 0}
    assert stored(store, session["id"])["status"] == "planned"  # time passing completes nothing
    out = training.complete_session(
        store,
        UID,
        session["id"],
        {"completed_on": "2020-01-07", "done": [0, 1], "note": "Felt fine."},
    )
    assert out["status"] == "completed" and out["completion"]["completed_on"] == "2020-01-07"
    assert [i["done"] for i in out["items"]] == [True, True] + [False] * (len(out["items"]) - 2)
    assert out["completion"]["note"] == "Felt fine."
    with pytest.raises(TrainingError, match="Reopen the session"):
        training.update_session(store, UID, session["id"], {"items": items_of(out)})
    back = training.update_session(store, UID, session["id"], {"status": "planned"})
    assert back["completion"] is None and not any(i["done"] for i in back["items"])


@pytest.mark.parametrize(
    "body,message",
    [
        ({}, "completion date"),
        ({"completed_on": "2026-11-16", "done": [99]}, "does not match"),
        ({"completed_on": "2026-11-16", "note": "x" * 301}, "under 300"),
        ({"completed_on": "2026-11-16", "video_id": "someone-elses"}, "Video not found"),
    ],
)
def test_a_completion_is_checked_before_it_is_recorded(store, body, message):
    store.videos["someone-elses"] = {"uid": OTHER, "status": "ready"}
    session = saved_week(store)["sessions"][0]
    with pytest.raises(TrainingError, match=message):
        training.complete_session(store, UID, session["id"], body)
    assert stored(store, session["id"])["status"] == "planned"


def test_skipped_cancelled_and_completed_sessions_are_counted_apart(store):
    a, b, c = (s["id"] for s in saved_week(store)["sessions"])
    training.complete_session(store, UID, a, {"completed_on": "2026-11-16"})
    training.update_session(store, UID, b, {"status": "skipped"})
    training.update_session(store, UID, c, {"status": "canceled"})
    over = training.overview(store, UID, MON)
    assert over["week"] | {"start": "", "end": ""} == {
        "start": "",
        "end": "",
        "planned": 0,
        "completed": 1,
        "skipped": 1,
        "canceled": 1,
    }
    assert [s["status"] for s in over["history"]] == ["canceled", "skipped", "completed"]
    assert over["upcoming"] == []
    with pytest.raises(TrainingError, match="cancelled or replaced"):
        training.complete_session(store, UID, c, {"completed_on": "2026-11-21"})
    # adherence is counted; nothing about technique is inferred from it anywhere
    assert "improv" not in str({k: over[k] for k in ("week", "history", "totals")}).lower()


def test_manual_sessions_are_the_swimmers_own_and_duplicates_are_caught(store):
    body = {
        "date": "2026-11-20",
        "time": "07:00",
        "title": "Club swim",
        "items": [
            {"activity_id": "", "name": "Club set", "minutes": 60},
            {"activity_id": "cool.easy_swim", "minutes": 5},
        ],
    }
    made = training.create_session(store, UID, body)
    assert made["origin"] == "manual" and made["basis"] is None and made["plan_id"] == ""
    assert all(i["source"] == "manual" and not i["recommendation_id"] for i in made["items"])
    assert made["minutes"] == 65
    with pytest.raises(TrainingError, match="already have a session"):
        training.create_session(store, UID, body)
    assert (
        training.create_session(store, UID, {**body, "allow_duplicate": True})["id"] != made["id"]
    )
    with pytest.raises(TrainingError, match="needs a date and a title"):
        training.create_session(store, UID, {"items": body["items"]})
    assert training.delete_session(store, UID, made["id"]) == {
        "deleted": True,
        "already_deleted": False,
    }
    assert training.delete_session(store, UID, made["id"])["already_deleted"] is True


def test_the_calendar_shows_stored_sessions_rest_days_and_refuses_huge_ranges(store):
    saved_week(store)
    cal = training.calendar(store, UID, date(2026, 11, 1), date(2026, 11, 30))
    assert [s["date"] for s in cal["sessions"]] == ["2026-11-16", "2026-11-18", "2026-11-21"]
    assert [r["date"] for r in cal["rest_days"]] == [
        "2026-11-17",
        "2026-11-19",
        "2026-11-20",
        "2026-11-22",
    ]
    assert training.calendar(store, UID, date(2026, 12, 1), date(2026, 12, 31))["sessions"] == []
    with pytest.raises(TrainingError, match="up to 100 days"):
        training.calendar(store, UID, date(2026, 1, 1), date(2026, 12, 31))


def test_nobody_can_read_or_change_another_swimmers_training(store):
    session = saved_week(store)["sessions"][0]
    for call in (
        lambda: training.update_session(store, OTHER, session["id"], {"title": "Mine now"}),
        lambda: training.complete_session(
            store, OTHER, session["id"], {"completed_on": "2026-11-16"}
        ),
        lambda: training.delete_session(store, OTHER, session["id"]),
    ):
        with pytest.raises(TrainingError) as e:
            call()
        assert e.value.status_code == 404 and e.value.detail == "Session not found."
    assert stored(store, session["id"])["title"] == session["title"]
    theirs = training.overview(store, OTHER, MON)
    assert theirs["plans"] == [] and theirs["upcoming"] == [] and theirs["history"] == []
    assert training.calendar(store, OTHER, MON, MON + timedelta(6))["sessions"] == []


# ---------- the analysis behind a plan, and deleting its video ----------


def add_video(
    store, vid="vid-a", uid=UID, supported=True, reliable=True, created="2026-11-10T10:00:00"
):
    """SYNTHETIC analysed video with a stored interpretation and feedback."""
    store.videos[vid] = {
        "uid": uid,
        "status": "ready",
        "storagePath": f"videos/{uid}/{vid}.mp4",
        "latestAnalysisId": "a1",
        "latestInterpretationId": "i1",
        "latestFeedbackId": "f1",
        "createdAt": created,
        "fileName": "SYNTHETIC test session.mp4",
    }
    store.analyses[(vid, "a1")] = {
        "uid": uid,
        "metrics": [{"key": "rhythm_variation", "status": "reliable" if reliable else "limited"}],
    }
    finding = {
        "id": "issue.timing.uneven_rhythm",
        "rule_id": "timing.uneven_rhythm",
        "title": "Stroke rhythm varies from cycle to cycle",
    }
    store.interpretations[(vid, "i1")] = {
        "uid": uid,
        "issue_candidates": [finding] if supported else [],
    }
    items = (
        [{"id": "fb.focus.x", "category": "focus", "finding_id": finding["id"]}]
        if supported
        else []
    )
    items.append({"id": "fb.obs", "category": "observation", "finding_id": "obs.body_line"})
    store.feedback[(vid, "f1")] = {
        "uid": uid,
        "items": items,
        "checkpoints": [{"id": "cp.recurs.x", "title": "Film again", "what_to_film": "Side view."}],
    }


def test_only_stored_supported_findings_reach_the_planner(store):
    assert training.analysis_context(store, UID).state == "none"
    add_video(store, supported=False)
    ctx = training.analysis_context(store, UID)
    assert ctx.state == "no_supported_issue" and ctx.findings == [] and ctx.checkpoints
    add_video(
        store, "vid-b", reliable=False, created="2026-11-12T10:00:00"
    )  # newest: nothing measurable
    assert training.analysis_context(store, UID).state == "unavailable"
    assert training.generate(store, UID, "week", MON).basis == "goal_based"
    add_video(store, "vid-c", created="2026-11-14T10:00:00")
    ctx = training.analysis_context(store, UID)
    assert ctx.state == "supported" and [f["rule_id"] for f in ctx.findings] == [
        "timing.uneven_rhythm"
    ]
    add_video(
        store, "vid-d", uid=OTHER, created="2026-11-15T10:00:00"
    )  # someone else's is never used
    assert training.analysis_context(store, UID).video_id == "vid-c"


def test_an_observation_or_a_limited_metric_never_becomes_a_corrective_recommendation(store):
    add_video(store, supported=False)
    store.feedback[("vid-a", "f1")]["items"].append(
        {"id": "fb.focus.arm", "category": "focus", "finding_id": "issue.arm"}
    )
    store.interpretations[("vid-a", "i1")]["issue_candidates"] = [
        {"id": "issue.arm", "rule_id": "pending.low_elbow", "title": "Elbow"}
    ]
    plan = training.generate(store, UID, "week", MON)
    assert plan.basis == "goal_based" and not any(r.finding_ids for r in plan.recommendations)


def test_deleting_a_video_keeps_the_training_and_removes_every_trace_of_the_video(store):
    add_video(store)
    plan = saved_week(store)
    assert plan["basis"] == "analysis_based" and plan["inputs"]["video_id"] == "vid-a"
    first = plan["sessions"][0]
    training.complete_session(
        store,
        UID,
        first["id"],
        {"completed_on": "2026-11-16", "note": "My note", "video_id": "vid-a"},
    )
    store.files["videos/swimmer-1/vid-a.mp4"] = b"x"
    assert jobs.delete_video(store, "vid-a", UID)["deleted"]
    assert "vid-a" not in store.videos
    text = str(store.docs)
    assert "vid-a" not in text and "Stroke rhythm varies" not in text and "cp.recurs.x" not in text
    kept = stored(store, first["id"])  # the swimmer's own record of the session is intact
    assert kept["status"] == "completed" and kept["completion"]["note"] == "My note"
    assert kept["linked_video_id"] == "" and kept["linked_video_removed"] is True
    shown = training.overview(store, UID, MON)["plans"][0]
    assert shown["inputs"]["analysis_removed"] is True and len(shown["sessions"]) == 3
    assert all(
        r["reason"] == training.REMOVED_REASON
        for r in shown["recommendations"]
        if r["basis"] == "analysis_based"
    )
    assert jobs.delete_video(store, "vid-a", UID)["already_deleted"] is True  # still safe to repeat
    assert training.generate(store, UID, "week", MON + timedelta(7)).basis == "goal_based"


def test_a_link_to_a_missing_video_is_never_returned_even_if_it_is_still_stored(store):
    add_video(store)
    session = saved_week(store)["sessions"][-1]
    training.complete_session(
        store, UID, session["id"], {"completed_on": "2026-11-21", "video_id": "vid-a"}
    )
    del store.videos["vid-a"]  # gone without the clean-up having run
    shown = training.calendar(store, UID, MON, MON + timedelta(6))["sessions"][-1]
    assert shown["linked_video_id"] == "" and shown["linked_video_removed"] is True
    assert (
        shown["checkpoint"]["source_video_id"] == "" and shown["checkpoint"]["checkpoint_ids"] == []
    )
    plan = training.overview(store, UID, MON)["plans"][0]
    assert plan["inputs"]["video_id"] == "" and "vid-a" not in str(plan)


def test_deleting_a_training_session_never_touches_a_video(store):
    add_video(store)
    session = saved_week(store)["sessions"][0]
    training.delete_session(store, UID, session["id"])
    assert "vid-a" in store.videos and store.analyses and store.feedback


def test_a_follow_up_video_changes_the_next_plan_only_through_stored_findings(store):
    add_video(store, supported=False)
    first = saved_week(store)
    assert first["basis"] == "goal_based"
    training.complete_session(
        store, UID, first["sessions"][0]["id"], {"completed_on": "2026-11-16"}
    )
    add_video(
        store, "vid-b", created="2026-11-22T10:00:00"
    )  # SYNTHETIC follow-up with a supported finding
    nxt = training.generate(store, UID, "week", MON + timedelta(7))
    assert nxt.basis == "analysis_based" and nxt.inputs.video_id == "vid-b"
    assert nxt.inputs.completed_before == 1
    assert (
        store.get_doc("training_plans", first["id"])["basis"] == "goal_based"
    )  # history untouched
    assert not re.search(
        r"because you (trained|completed)|thanks to your training", all_text(nxt), re.I
    )
