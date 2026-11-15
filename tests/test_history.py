"""Comparing sessions, progress series, checkpoint follow-up and deletion.

Every 'session' here is a synthetic fixture built from the synthetic swimmer, with values
edited to known differences. They test the software's logic. They are not a swimmer's
progress and say nothing about whether anyone improved."""

import pytest
from test_interpretation import EVEN, UNEVEN, metric, result

from aquatrack.analysis.comparison import Session, build_progress, compare, follow_up
from aquatrack.analysis.feedback import build_feedback
from aquatrack.analysis.interpretation import SwimmerContext, interpret
from aquatrack.api import jobs
from aquatrack.api.jobs import JobRequestError, request_analysis, run_job
from aquatrack.contracts import MetricStatus, QualityGrade

UID, OTHER = "swimmer-1", "swimmer-2"


def session(vid="s", day=1, times=EVEN, edit=None, **session_fields) -> Session:
    r = result(times, **session_fields)
    for key, value in (edit or {}).items():
        metric(r, key).value = value
    return Session(vid, r, f"a-{vid}", f"2026-10-{day:02d}T10:00:00+00:00", synthetic=True)


def states(c) -> dict[str, str]:
    return {m.metric_key: m.state for m in c.metrics}


# ---------- comparison ----------


def test_compatible_sessions_are_compared_metric_by_metric_in_neutral_words():
    before = session("a", 1)
    leg = metric(before.result, "leg_line_angle").value
    now = session(
        "b",
        8,
        edit={
            "leg_line_angle": leg + 9.0,
            "head_height": metric(before.result, "head_height").value + 0.02,
        },
    )
    c = compare(now, before)
    assert c.comparable and c.session_reasons == [] and c.comparison_version == "1.0"
    s = states(c)
    assert s["leg_line_angle"] == "increased" and s["head_height"] == "no_clear_change"
    assert s["stroke_rate"] == "no_clear_change" and s["pull_depth"] == "not_comparable"
    m = next(x for x in c.metrics if x.metric_key == "leg_line_angle")
    assert (m.previous, m.current, m.change) == (leg, leg + 9.0, 9.0) and m.threshold >= 4.0
    assert m.relative_pct is None and m.previous_status == m.current_status == "reliable"
    assert any("not whether it is better" in text for text in m.limitations)
    assert next(x for x in c.metrics if x.metric_key == "stroke_rate").relative_pct == 0.0
    text = c.model_dump_json().lower()
    assert not any(word in text for word in ('"improved"', '"worse"', '"better"', "deteriorat"))
    assert (c.previous.video_id, c.current.video_id, c.previous.analysis_id) == ("a", "b", "a-a")


def test_a_decrease_is_reported_as_a_decrease_not_as_progress():
    before = session("a", 1)
    now = session(
        "b", 8, edit={"leg_line_angle": metric(before.result, "leg_line_angle").value - 9.0}
    )
    assert states(compare(now, before))["leg_line_angle"] == "decreased"


@pytest.mark.parametrize(
    ("fields", "expect"),
    [
        ({"stroke": "Backstroke"}, "Different stroke"),
        ({"camera": "Overhead"}, "Different filming angle"),
        ({"distance": "200 m"}, "Different distance"),
    ],
)
def test_sessions_that_differ_as_a_whole_are_not_compared_and_say_exactly_why(fields, expect):
    c = compare(session("b", 8), session("a", 1, **fields))
    assert not c.comparable and any(expect in r for r in c.session_reasons)
    assert set(states(c).values()) == {"not_comparable"}
    assert all(m.change is None and m.reasons == c.session_reasons for m in c.metrics)
    assert "cannot be compared" in c.summary


def test_different_effort_is_not_compared_even_with_the_same_labels():
    easy = session("a", 1, [2.4, 2.5, 2.5, 2.6, 2.5, 2.5, 2.4])
    sprint = session("b", 8, [1.1, 1.1, 1.15, 1.1, 1.05, 1.1, 1.1])
    c = compare(sprint, easy)
    assert not c.comparable and "A different effort" in c.session_reasons[0]


def test_one_metric_can_be_comparable_while_another_is_not():
    before, now = session("a", 1), session("b", 8)
    now.result.coverage.view.status = "changing"  # body position off, timing still fine
    metric(now.result, "rhythm_variation").status = MetricStatus.LIMITED
    metric(now.result, "rhythm_variation").reason = "Only 3 stroke cycles."
    c = compare(now, before)
    s = states(c)
    assert c.comparable and s["stroke_rate"] == "no_clear_change"
    assert (
        s["leg_line_angle"] == "not_comparable" and s["rhythm_variation"] == "insufficient_evidence"
    )
    leg = next(m for m in c.metrics if m.metric_key == "leg_line_angle")
    assert "camera view changed" in leg.reasons[0]
    rhythm = next(m for m in c.metrics if m.metric_key == "rhythm_variation")
    assert "Limited in the later swim" in rhythm.reasons[0]


def test_metric_definitions_that_changed_between_versions_are_not_compared():
    before, now = session("a", 1), session("b", 8)
    before.result.schema_version = "1.1"
    s = states(compare(now, before))
    assert s["stroke_rate"] == "no_clear_change"  # defined the same way since 1.1
    assert s["leg_line_angle"] == "not_comparable"  # redefined in 1.2: no silent conversion
    leg = next(m for m in compare(now, before).metrics if m.metric_key == "leg_line_angle")
    assert "defined differently before analysis version 1.2" in leg.reasons[0]

    old = session("c", 1)
    old.result.schema_version, old.result.metrics, old.result.coverage = "1.0", [], None
    c = compare(now, old)
    assert not c.comparable and "before technique measurements existed" in c.session_reasons[0]


def test_differences_inside_measurement_noise_are_no_clear_change():
    before = session("a", 1)
    now = session(
        "b",
        8,
        edit={
            "leg_line_angle": metric(before.result, "leg_line_angle").value + 3.0,
            "cycle_duration": metric(before.result, "cycle_duration").value + 0.05,
        },
    )
    s = states(compare(now, before))
    assert s["leg_line_angle"] == "no_clear_change" and s["cycle_duration"] == "no_clear_change"


# ---------- progress ----------


def test_no_videos_and_one_video_are_a_baseline_with_nothing_invented():
    empty = build_progress([], 0)
    assert empty.baseline and empty.series == [] and empty.note == "No analysed videos yet."
    one = build_progress([session("a", 1)], 1)
    assert one.baseline and len(one.series) == 1 and "baseline" in one.note
    assert all(len(m.points) == 1 and m.overall is None for m in one.series[0].metrics)


def test_compatible_sessions_share_a_series_and_incompatible_ones_never_join_it():
    a = session("a", 1)
    leg = metric(a.result, "leg_line_angle").value
    sessions = [
        a,
        session("b", 8, edit={"leg_line_angle": leg + 5.0}),
        session("c", 15, edit={"leg_line_angle": leg + 10.0}),
        session("sprint", 16, [0.8, 0.8, 0.84, 0.8, 0.76, 0.8, 0.8]),  # 75/min against 50/min
        session("back", 17, stroke="Backstroke"),
    ]
    p = build_progress(sessions, 5)
    assert not p.baseline and [len(s.sessions) for s in p.series] == [3, 1, 1]
    main = p.series[0]
    leg_metric = next(m for m in main.metrics if m.metric_key == "leg_line_angle")
    assert [pt.video_id for pt in leg_metric.points] == ["a", "b", "c"]  # oldest first
    assert [pt.value for pt in leg_metric.points] == [leg, leg + 5.0, leg + 10.0]
    assert leg_metric.overall.state == "increased" and leg_metric.overall.change == 10.0
    ids = {pt.video_id for s in p.series for m in s.metrics for pt in m.points}
    # Every point is a stored session. Backstroke gets a series but no points: its
    # measurements are only "limited" (checked on freestyle only), so nothing is drawn.
    assert ids == {"a", "b", "c", "sprint"} and p.series[2].metrics == []
    assert not ({"sprint", "back"} & {s.video_id for s in main.sessions})


def test_unreliable_or_distorted_values_are_left_off_the_line_not_drawn():
    a, b, c = session("a", 1), session("b", 8), session("c", 15)
    b.result.coverage.view.status = "changing"
    metric(c.result, "leg_line_angle").status = MetricStatus.LIMITED
    weak = session("weak", 20)
    weak.result.quality.grade = QualityGrade.INSUFFICIENT
    p = build_progress([a, b, c, weak, session("d", 22)], 5)
    leg = next(m for m in p.series[0].metrics if m.metric_key == "leg_line_angle")
    assert [pt.video_id for pt in leg.points] == ["a", "d"]
    rate = next(m for m in p.series[0].metrics if m.metric_key == "stroke_rate")
    assert [pt.video_id for pt in rate.points] == ["a", "b", "c", "d"]  # timing is unaffected
    assert [s.video_id for s in p.not_in_any_series] == ["weak"]
    assert "could not be followed" in p.not_included_reasons["weak"][0]


def test_repeated_limitations_are_reported_as_filming_issues_not_technique():
    sessions = [session(v, d) for v, d in (("a", 1), ("b", 8), ("c", 15))]
    for s in sessions[:2]:
        s.result.coverage.view.status = "changing"
    p = build_progress(sessions, 3)
    assert (
        len(p.repeated_limitations) == 1
        and "camera view changed during 2 of your 3" in p.repeated_limitations[0]
    )
    assert "Filming" in p.repeated_limitations[0]


# ---------- recurrence strengthens a supported issue, and nothing else ----------


def test_a_pattern_that_recurs_in_compatible_swims_can_become_a_priority_without_a_goal():
    alone = interpret(result(UNEVEN), "v")
    assert len(alone.issue_candidates) == 1 and alone.priorities == []
    again = interpret(
        result(UNEVEN),
        "v",
        history=[jobs.PriorSession("e1", result(UNEVEN)), jobs.PriorSession("e2", result(UNEVEN))],
    )
    issue = again.issue_candidates[0]
    assert (
        issue.recurrences == 2
        and "found in 2 of your earlier comparable swims" in issue.description
    )
    assert [p.finding_id for p in again.priorities] == ["issue.timing.uneven_rhythm"]
    seen = next(f for f in again.priorities[0].factors if f.name == "Seen across swims")
    assert seen.points == 2 and again.rules_version.endswith("-2")
    assert "Worth a look" in issue.description  # still not called a fault


def test_values_that_stay_the_same_across_swims_never_become_an_issue():
    r = result(EVEN)
    metric(r, "body_line_angle").value = 30.0  # the same unusual value every time
    history = [jobs.PriorSession(f"e{k}", r.model_copy(deep=True)) for k in range(3)]
    i = interpret(
        r.model_copy(deep=True),
        "v",
        context=SwimmerContext(goals=["body_alignment"]),
        history=history,
    )
    assert i.issue_candidates == [] and i.priorities == []
    steady = next(f for f in i.observations if f.id == "obs.history.body_line_angle")
    assert "steady across your last 4 comparable swims" in steady.title


# ---------- checkpoints followed up ----------


def stored_checkpoints(s: Session) -> list[dict]:
    return [
        c.model_dump()
        for c in build_feedback(interpret(s.result, s.video_id, s.analysis_id), "i").checkpoints
    ]


def test_checkpoints_record_their_baseline_and_origin():
    a = session("a", 1)
    cps = stored_checkpoints(a)
    repeat = next(c for c in cps if c["id"] == "cp.repeat_same_conditions")
    assert (
        repeat["source_video_id"] == "a"
        and repeat["source_analysis_id"] == "a-a"
        and repeat["created_at"]
    )
    assert "baseline" in repeat["reason"]
    assert {b["metric_key"] for b in repeat["baseline"]} >= {"cycle_duration", "leg_line_angle"}
    leg = next(b for b in repeat["baseline"] if b["metric_key"] == "leg_line_angle")
    assert leg["value"] == metric(a.result, "leg_line_angle").value


def test_a_later_compatible_video_answers_the_checkpoint_in_neutral_states():
    a = session("a", 1)
    cps = stored_checkpoints(a)
    same = follow_up(cps, a, session("b", 8))
    assert (
        next(f for f in same if f.checkpoint_id == "cp.repeat_same_conditions").state
        == "no_clear_measurable_change"
    )
    moved = follow_up(
        cps,
        a,
        session("c", 9, edit={"leg_line_angle": metric(a.result, "leg_line_angle").value + 9.0}),
    )
    f = next(x for x in moved if x.checkpoint_id == "cp.repeat_same_conditions")
    assert f.state == "measurable_change_observed" and f.source_video_id == "a"
    assert (
        "not that it is better or worse" in f.explanation and "improv" not in f.explanation.lower()
    )
    assert any(m.metric_key == "leg_line_angle" and m.state == "increased" for m in f.metrics)


def test_an_unsuitable_later_video_cannot_evaluate_the_checkpoint_and_says_why():
    a = session("a", 1)
    cps = stored_checkpoints(a)
    other = follow_up(cps, a, session("b", 8, stroke="Backstroke"))
    f = next(x for x in other if x.checkpoint_id == "cp.repeat_same_conditions")
    assert f.state == "cannot_evaluate" and "Different stroke" in f.explanation

    short = session("s", 1)
    for key in ("cycle_duration", "stroke_rate", "rhythm_variation"):
        metric(short.result, key).n_cycles = 3
    cps = stored_checkpoints(short)
    assert any(c["id"] == "cp.longer_clip" for c in cps)
    still_short = follow_up(cps, short, short)
    assert (
        next(x for x in still_short if x.checkpoint_id == "cp.longer_clip").state
        == "cannot_evaluate"
    )
    long_enough = follow_up(cps, short, session("l", 8))
    assert (
        next(x for x in long_enough if x.checkpoint_id == "cp.longer_clip").state
        == "comparable_measurement_available"
    )


# ---------- store-level: history, follow-ups, deletion ----------


@pytest.fixture
def two_videos(store, source):
    """The same synthetic clip analysed as two uploads a week apart (a labelled fixture)."""
    request_analysis(store, "vid1", UID)
    run_job(store, source, "vid1")
    store.videos["vid1"]["createdAt"] = "2026-11-01T10:00:00+00:00"
    store.videos["vid2"] = {
        k: v
        for k, v in store.videos["vid1"].items()
        if k
        in (
            "uid",
            "storagePath",
            "contentType",
            "sizeBytes",
            "stroke",
            "camera",
            "distance",
            "poolLength",
        )
    }
    store.videos["vid2"] |= {"status": "uploaded", "createdAt": "2026-11-08T10:00:00+00:00"}
    request_analysis(store, "vid2", UID)
    run_job(store, source, "vid2")
    return store


@pytest.fixture
def store(swim_video):
    from aquatrack.api.store import MemoryStore

    s = MemoryStore()
    path = f"videos/{UID}/vid1.mp4"
    s.files[path] = swim_video.read_bytes()
    s.videos["vid1"] = {
        "uid": UID,
        "storagePath": path,
        "status": "uploaded",
        "contentType": "video/mp4",
        "sizeBytes": len(s.files[path]),
        "stroke": "Freestyle",
        "camera": "Underwater",
        "distance": "50 m",
        "poolLength": "25 m",
        "createdAt": "2026-11-01T10:00:00+00:00",
    }
    return s


@pytest.fixture
def source(tmp_path, swim_video):
    from conftest import make_raw_pose

    from aquatrack.analysis.pose.sources import PrecomputedPoseSource
    from aquatrack.analysis.video import video_identity

    src = PrecomputedPoseSource(tmp_path / "poses")
    src.directory.mkdir()
    make_raw_pose(swim_video).save(src.path_for(video_identity(swim_video).sha256))
    return src


def test_the_second_video_follows_up_the_firsts_checkpoints_and_history_is_kept(two_videos):
    store = two_videos
    first = store.feedback[("vid1", store.videos["vid1"]["latestFeedbackId"])]
    second = store.feedback[("vid2", store.videos["vid2"]["latestFeedbackId"])]
    assert first["followups"] == [] and first["checkpoints"]  # the first one is untouched
    ups = second["followups"]
    assert ups and all(u["source_video_id"] == "vid1" for u in ups)
    assert {u["state"] for u in ups} <= {
        "no_clear_measurable_change",
        "comparable_measurement_available",
        "cannot_evaluate",
        "measurable_change_observed",
    }
    repeat = next(u for u in ups if u["checkpoint_id"] == "cp.repeat_same_conditions")
    assert repeat["state"] == "no_clear_measurable_change"  # the very same clip
    interp = store.interpretations[("vid2", store.videos["vid2"]["latestInterpretationId"])]
    assert interp["baseline"] is False and interp["sessions"][0]["video_id"] == "vid1"


def test_compare_and_progress_use_only_the_callers_own_videos(two_videos):
    store = two_videos
    c = jobs.compare_videos(store, UID, "vid2", "vid1")
    assert (c["previous"]["video_id"], c["current"]["video_id"]) == ("vid1", "vid2") and c[
        "comparable"
    ]
    assert (
        jobs.compare_videos(store, UID, "vid1", "vid2")["previous"]["video_id"] == "vid1"
    )  # order by date
    for bad in (("vid1", "vid1"), ("vid1", "nope")):
        with pytest.raises(JobRequestError) as e:
            jobs.compare_videos(store, UID, *bad)
        assert e.value.status_code == 404
    with pytest.raises(JobRequestError) as e:
        jobs.compare_videos(store, OTHER, "vid1", "vid2")
    assert e.value.status_code == 404
    mine = jobs.progress_for(store, UID)
    assert mine["progress"]["analyzed"] == 2 and not mine["progress"]["baseline"]
    assert [h["video_id"] for h in mine["history"]] == ["vid1", "vid2"] and mine[
        "latest_video_id"
    ] == "vid2"
    assert mine["open_checkpoints"] and mine["followups"]
    theirs = jobs.progress_for(store, OTHER)
    assert (
        theirs["progress"]["analyzed"] == 0
        and theirs["history"] == []
        and theirs["open_checkpoints"] == []
    )
    assert "storage" not in str(mine).lower() and "videos/" not in str(mine)


def test_deleting_a_video_removes_everything_stored_for_it_and_nothing_else(two_videos):
    store = two_videos
    kept = {k: dict(v) for k, v in store.feedback.items() if k[0] == "vid1"}
    assert any(p.startswith(f"analysis/{UID}/vid2/") for p in store.files)
    out = jobs.delete_video(store, "vid2", UID)
    assert out == {"deleted": True, "already_deleted": False}
    assert "vid2" not in store.videos
    for table in (store.analyses, store.interpretations, store.feedback):
        assert not any(k[0] == "vid2" for k in table)
    assert not any("/vid2/" in p for p in store.files)
    # The other video is untouched, file and all (both uploads share one file path here,
    # so check the records and artifacts).
    assert (
        "vid1" in store.videos
        and {k: v for k, v in store.feedback.items() if k[0] == "vid1"} == kept
    )
    assert any(p.startswith(f"analysis/{UID}/vid1/") for p in store.files)
    assert jobs.delete_video(store, "vid2", UID) == {
        "deleted": True,
        "already_deleted": True,
    }  # idempotent
    after = jobs.progress_for(store, UID)
    assert [h["video_id"] for h in after["history"]] == ["vid1"] and after["progress"]["baseline"]


def test_nobody_can_delete_someone_elses_video(two_videos):
    store = two_videos
    with pytest.raises(JobRequestError) as e:
        jobs.delete_video(store, "vid1", OTHER)
    assert e.value.status_code == 404 and e.value.detail == "Video not found."
    assert store.videos["vid1"]["status"] == "ready" and any(k[0] == "vid1" for k in store.analyses)


@pytest.mark.parametrize("step", ["artifacts", "video_file", "documents", "record"])
def test_a_deletion_that_fails_part_way_can_be_finished_by_asking_again(two_videos, step):
    store = two_videos
    store.fail_delete_at = step
    with pytest.raises(JobRequestError) as e:
        jobs.delete_video(store, "vid2", UID)
    assert e.value.status_code == 503 and "videos/" not in e.value.detail  # no paths leak
    assert store.videos["vid2"]["status"] == "deleting"  # still findable, and locked
    with pytest.raises(JobRequestError) as locked:
        request_analysis(store, "vid2", UID, rerun=True)
    assert locked.value.status_code == 409 and "being deleted" in locked.value.detail
    store.fail_delete_at = None
    assert jobs.delete_video(store, "vid2", UID) == {"deleted": True, "already_deleted": False}
    assert "vid2" not in store.videos and not any(k[0] == "vid2" for k in store.analyses)


def test_an_analysis_that_finishes_after_deletion_started_stores_nothing(
    store, source, monkeypatch
):
    request_analysis(store, "vid1", UID)
    real = jobs.analyze

    def analyze_then_user_deletes(*args, **kwargs):
        out = real(*args, **kwargs)
        store.videos["vid1"]["status"] = "deleting"  # the delete request lands mid-analysis
        return out

    monkeypatch.setattr(jobs, "analyze", analyze_then_user_deletes)
    run_job(store, source, "vid1")
    assert store.analyses == {} and store.interpretations == {} and store.feedback == {}
    assert not any(p.startswith("analysis/") for p in store.files)
    assert store.videos["vid1"]["status"] == "deleting"  # not flipped back to ready
    jobs.delete_video(store, "vid1", UID)
    store.update_video("vid1", {"status": "ready"})  # a late write must not bring it back
    assert "vid1" not in store.videos
