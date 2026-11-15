"""The interpretation layer on stored analysis results: what it says, and what it refuses
to say. Results come from the synthetic swimmer; where a test needs particular cycle times
or an earlier swim, the stored metrics are edited directly, which is all the layer reads.
Every earlier swim here is a labelled fixture, never real progress."""

import re

import numpy as np
import pytest
from test_biomechanics import FREESTYLE, run, side_view

from aquatrack.analysis import interpretation as interp
from aquatrack.analysis.interpretation import PriorSession, SwimmerContext, interpret
from aquatrack.contracts import AnalysisResult, Interpretation, MetricStatus, SessionInfo

EVEN = [1.20, 1.20, 1.24, 1.16, 1.20, 1.20, 1.20]
UNEVEN = [1.20, 1.44, 1.20, 0.98, 1.20, 1.40, 1.20]  # three cycles well off the middle
# Far more uneven: with seven cycles a variation value is itself uncertain, so only a large
# rise over an earlier swim counts as a change.
WILD = [1.20, 1.80, 1.20, 0.75, 1.20, 1.80, 1.20]


def result(times=None, **session) -> AnalysisResult:
    r, _ = run(
        side_view(travel=1.0),
        SessionInfo(
            **({"stroke": "Freestyle", "camera": "Underwater", "distance": "50 m"} | session)
        ),
    )
    return with_cycle_times(r, times) if times else r


def with_cycle_times(r: AnalysisResult, times) -> AnalysisResult:
    r = r.model_copy(deep=True)
    m = {x.key: x for x in r.metrics}
    samples = m["cycle_duration"].samples
    times = [times[k % len(times)] for k in range(len(samples))]  # as many as there are cycles
    for sample, value in zip(samples, times, strict=True):
        sample.value = value
    m["cycle_duration"].value = float(np.median(times))
    m["stroke_rate"].value = round(60 / float(np.median(times)), 1)
    m["rhythm_variation"].value = round(100 * float(np.std(times, ddof=1) / np.mean(times)), 1)
    return r


def metric(r: AnalysisResult, key: str):
    return next(m for m in r.metrics if m.key == key)


def prior(r: AnalysisResult, video_id="earlier") -> PriorSession:
    return PriorSession(video_id=video_id, result=r, recorded_at="2026-10-01", synthetic=True)


def rule(i: Interpretation, rule_id: str):
    return next(x for x in i.rules if x.rule_id == rule_id)


# ---------- level 1: observations ----------


def test_observations_describe_and_never_judge():
    i = interpret(result(), "v")
    assert {f.id for f in i.observations} >= {
        "obs.stroke_tempo",
        "obs.rhythm",
        "obs.leg_line",
        "obs.head",
    }
    assert i.issue_candidates == [] and i.priorities == []
    judging = re.compile(
        r"\b(should|too (high|low|much|little)|incorrect|wrong|poor|bad|fix|improve|inefficient)\b"
    )
    for f in i.observations:
        text = f"{f.title} {f.description}".lower()
        assert not judging.search(text), text
        assert f.level == "observation" and not f.actionable
        assert f.evidence and all(e.metric_key for e in f.evidence)
        assert f.withheld, "every observation says what it does not claim"
    tempo = next(f for f in i.observations if f.id == "obs.stroke_tempo")
    assert "50.0 full arm cycles per minute" in tempo.description
    assert any("not good or bad by itself" in text for text in tempo.limitations)


def test_no_score_and_no_ideal_values_exist_anywhere():
    doc = interpret(result(UNEVEN), "v").to_firestore()
    assert not any(k in doc for k in ("technique_score", "grade", "rating"))
    assert all(
        r.metric_keys and set(r.metric_keys) <= interp.ISSUE_ELIGIBLE
        for r in interp.RULES
        if r.active
    )
    assert not (interp.ISSUE_ELIGIBLE & interp.CONTEXT_ONLY)


def test_a_steady_rhythm_is_reported_as_steady_within_what_can_be_timed():
    i = interpret(result(EVEN), "v")
    rhythm = next(f for f in i.observations if f.id == "obs.rhythm")
    assert (
        rhythm.title.startswith("Rhythm steady")
        and "frames per second can time" in rhythm.description
    )
    assert rule(i, "timing.uneven_rhythm").state == "not_triggered"


# ---------- level 2: issue candidates ----------


def test_repeated_off_rhythm_cycles_become_an_issue_candidate_with_their_timestamps():
    i = interpret(result(UNEVEN), "v")
    assert [f.id for f in i.issue_candidates] == ["issue.timing.uneven_rhythm"]
    issue = i.issue_candidates[0]
    assert issue.level == "issue_candidate" and issue.actionable
    odd = next(e for e in issue.evidence if e.label == "Cycles off the rhythm")
    assert odd.n_cycles == 3 and [s.value for s in odd.samples] == [1.44, 0.98, 1.40]
    assert all(s.t_s >= 0 for s in odd.samples)
    assert "own middle cycle time" in issue.description
    assert any("not known" in text for text in issue.withheld)
    assert rule(i, "timing.uneven_rhythm").state == "triggered"


def test_one_odd_cycle_or_too_few_cycles_is_not_an_issue():
    one_off = [1.20, 1.20, 1.50, 1.20, 1.20, 1.20, 1.20]
    i = interpret(result(one_off), "v")
    assert i.issue_candidates == [] and rule(i, "timing.uneven_rhythm").state == "not_triggered"

    r = result(UNEVEN)
    for key in ("cycle_duration", "rhythm_variation"):
        metric(r, key).n_cycles = 5
    i = interpret(r, "v")
    assert i.issue_candidates == []
    assert rule(i, "timing.uneven_rhythm").state == "not_applicable"
    assert "at least 6" in rule(i, "timing.uneven_rhythm").reason


def test_differences_smaller_than_the_timing_resolution_do_not_count():
    # 0.10 s is 2.5 frames at 25 fps: under the 3 frames a cycle must differ by.
    wobble = [1.20, 1.30, 1.20, 1.10, 1.20, 1.30, 1.20]
    i = interpret(result(wobble), "v")
    assert i.issue_candidates == []


def test_limited_and_unavailable_metrics_never_trigger_anything():
    r = result(UNEVEN)
    metric(r, "rhythm_variation").status = MetricStatus.LIMITED
    metric(r, "rhythm_variation").reason = "Only 3 stroke cycles."
    i = interpret(r, "v")
    assert i.issue_candidates == []
    assert rule(i, "timing.uneven_rhythm").state == "not_applicable"
    rhythm = next(f for f in i.observations if f.id == "obs.rhythm")
    assert rhythm.evidence_class == "context_only"  # still described, for information
    assert any(u.key == "limited.rhythm_variation" for u in i.undetermined)

    r = result(UNEVEN)
    for m in r.metrics:
        m.status, m.value, m.samples, m.reason = (
            MetricStatus.UNAVAILABLE,
            None,
            [],
            "Could not be followed.",
        )
    i = interpret(r, "v")
    assert i.observations == [] and i.issue_candidates == [] and i.priorities == []
    grouped = [u for u in i.undetermined if u.reason == "Could not be followed."]
    assert len(grouped) == 1 and "Stroke rate" in grouped[0].title  # said once, not eleven times


def test_arm_metrics_are_context_only_whatever_their_values():
    r = result()
    metric(r, "elbow_angle_min").value = 40.0  # an extreme bend
    metric(r, "pull_depth").value = 2.5
    metric(r, "pull_path_variation").value = 0.9
    i = interpret(r, "v", history=[prior(result())])
    arm = next(f for f in i.observations if f.id == "obs.arm_pull_context")
    assert arm.evidence_class == "context_only" and not arm.actionable
    assert i.issue_candidates == [] and i.priorities == []
    assert not any(
        k in f.metric_keys
        for f in i.observations
        if f.category == "history"
        for k in interp.CONTEXT_ONLY
    )
    assert rule(i, "pending.arm_pull").state == "pending_validation"


def test_extreme_body_angles_are_described_not_judged():
    r = result()
    metric(r, "body_line_angle").value = 35.0
    metric(r, "leg_line_angle").value = -30.0
    i = interpret(r, "v")
    assert i.issue_candidates == []
    assert rule(i, "pending.body_line_direction").state == "pending_validation"
    assert "verified source" in rule(i, "pending.body_line_direction").reason


# ---------- camera view ----------


def test_a_changing_camera_view_limits_interpretation_and_is_not_a_technique_problem():
    r = result(UNEVEN)
    r.coverage.view.status = "changing"
    r.coverage.view.note = "The swimmer's size in the picture changes a lot."
    i = interpret(r, "v", history=[prior(result(EVEN))])
    assert i.issue_candidates == []
    assert rule(i, "timing.uneven_rhythm").state == "suppressed"
    assert "filming" in rule(i, "timing.uneven_rhythm").reason
    for f in i.observations:
        if f.category == "body_position":
            assert f.evidence_class == "context_only"
            assert "camera view changed" in f.limitations[0]
    # Picture measurements are not compared with earlier swims either.
    compared = {k for f in i.observations if f.category == "history" for k in f.metric_keys}
    assert not (compared & interp.GEOMETRIC)
    view = next(u for u in i.undetermined if u.key == "camera_view")
    assert view.kind == "measurement" and "nothing about posture is concluded" in view.reason


# ---------- personal context ----------


def test_missing_profile_and_missing_goals_invent_nothing():
    none = interpret(result(UNEVEN), "v")
    assert none.context.swim_level is None and none.context.goals == []
    assert "No swimmer profile was available." in none.context.notes
    assert none.priorities == [] and any(u.key == "no_goals" for u in none.undetermined)

    level = interpret(result(UNEVEN), "v", context=SwimmerContext(swim_level="beginner"))
    assert level.context.swim_level == "beginner"
    assert [f.id for f in level.issue_candidates] == [f.id for f in none.issue_candidates]
    assert [f.description for f in level.observations] == [f.description for f in none.observations]
    assert any("does not change any finding" in n for n in level.context.notes)


def test_profile_goals_and_personal_bests_are_used_only_where_they_apply():
    pbs = [
        {"event": "50 Free", "pool": "25 m", "seconds": 31.2},
        {"event": "100 Back", "pool": "25 m", "seconds": 80.0},
    ]
    ctx = SwimmerContext(
        swim_level="masters", pbs=pbs, goals=["stroke_consistency", "not_a_real_goal"]
    )
    i = interpret(result(UNEVEN), "v", context=ctx)
    assert i.context.goals == ["stroke_consistency"]  # unknown goals are dropped, not guessed at
    assert (i.context.personal_best_event, i.context.personal_best_s) == ("50 Free", 31.2)
    assert i.issue_candidates[0].context_used == ["stroke consistency"]
    assert [p.finding_id for p in i.priorities] == ["issue.timing.uneven_rhythm"]

    other_goal = interpret(result(UNEVEN), "v", context=SwimmerContext(goals=["arm_technique"]))
    assert other_goal.priorities == []  # a goal the finding does not relate to adds nothing


# ---------- history ----------


def test_first_swim_is_a_baseline():
    i = interpret(result(), "v", history=[])
    assert i.baseline and i.sessions == []
    assert any(u.key == "no_history" and "baseline" in u.reason for u in i.undetermined)
    assert rule(i, "history.rhythm_less_steady").state == "not_applicable"
    assert not any(f.category == "history" for f in i.observations)


def test_a_compatible_earlier_swim_is_compared_metric_by_metric():
    earlier = result(EVEN)
    metric(earlier, "leg_line_angle").value = -12.0
    now = result(WILD)
    i = interpret(now, "v", history=[prior(earlier)])
    assert not i.baseline and [(s.compatible, s.synthetic) for s in i.sessions] == [(True, True)]
    changed = {f.metric_keys[0]: f for f in i.observations if f.category == "history"}
    assert "changed since" in changed["leg_line_angle"].title
    assert changed["leg_line_angle"].changes[0].before == -12.0
    assert "Not judged as better or worse." in changed["leg_line_angle"].withheld
    assert "no clear change" in changed["head_height"].title
    issue = next(f for f in i.issue_candidates if f.id == "issue.history.rhythm_less_steady")
    assert issue.changes[0].changed and issue.changes[0].now > issue.changes[0].before
    assert "does not say why" in issue.withheld[0]


def test_a_change_smaller_than_noise_is_no_change():
    earlier, now = result(EVEN), result(EVEN)
    metric(now, "leg_line_angle").value = (
        metric(earlier, "leg_line_angle").value + 3.0
    )  # under 2 x 2 degrees
    metric(now, "rhythm_variation").value = metric(earlier, "rhythm_variation").value + 0.8
    i = interpret(now, "v", history=[prior(earlier)])
    leg = next(f for f in i.observations if f.id == "obs.history.leg_line_angle")
    assert not leg.changes[0].changed and "cannot be told from measurement noise" in leg.description
    assert rule(i, "history.rhythm_less_steady").state == "not_triggered"
    assert i.issue_candidates == []


@pytest.mark.parametrize(
    ("change", "expect"),
    [
        ({"stroke": "Backstroke"}, "Different stroke"),
        ({"camera": "Overhead"}, "Different filming angle"),
        ({"distance": "200 m"}, "Different distance"),
    ],
)
def test_incompatible_sessions_are_listed_with_the_reason_and_not_used(change, expect):
    earlier = result(EVEN, **change)
    i = interpret(result(UNEVEN), "v", history=[prior(earlier)])
    assert i.baseline and not i.sessions[0].compatible
    assert any(expect in reason for reason in i.sessions[0].reasons)
    assert not any(f.category == "history" for f in i.observations)
    assert rule(i, "history.rhythm_less_steady").state == "not_applicable"
    assert (
        "set aside as not comparable"
        in next(u for u in i.undetermined if u.key == "no_history").reason
    )


def test_a_sprint_and_an_easy_swim_are_not_compared():
    easy = result([2.4, 2.5, 2.5, 2.6, 2.5, 2.5, 2.4])
    sprint = result([1.1, 1.1, 1.15, 1.1, 1.05, 1.1, 1.1])
    i = interpret(sprint, "v", history=[prior(easy)])
    assert i.baseline and "A different effort" in i.sessions[0].reasons[0]


def test_a_different_analysis_version_is_not_compared():
    earlier = result(EVEN)
    earlier.schema_version = "1.1"
    i = interpret(result(UNEVEN), "v", history=[prior(earlier)])
    assert not i.sessions[0].compatible
    assert "different version of the analysis" in i.sessions[0].reasons[0]


def test_results_from_before_metrics_existed_are_read_without_inventing_findings():
    old = result()
    old.schema_version, old.metrics, old.coverage = "1.0", [], None
    i = interpret(old, "v", history=[prior(result())])
    assert i.observations == [] and i.issue_candidates == [] and i.priorities == []
    assert i.analysis_schema_version == "1.0"
    assert any(u.key == "no_metrics" for u in i.undetermined)
    assert all(r.state in ("not_applicable", "pending_validation") for r in i.rules)


# ---------- level 3: priorities ----------


def test_an_issue_from_one_clip_with_no_goal_is_not_a_priority():
    i = interpret(result(UNEVEN), "v")
    assert len(i.issue_candidates) == 1 and i.priorities == []
    assert "nothing is ranked as a priority" in i.priorities_note


def test_no_issues_means_no_priorities_and_says_so():
    i = interpret(result(EVEN), "v", context=SwimmerContext(goals=["stroke_consistency"]))
    assert i.priorities == [] and "do not support any" in i.priorities_note


def test_priorities_are_ranked_by_visible_points_and_capped_at_three():
    earlier, older = result(EVEN), result(EVEN)
    ctx = SwimmerContext(goals=["stroke_consistency"])
    i = interpret(
        result(WILD), "v", context=ctx, history=[prior(earlier, "e1"), prior(older, "e2")]
    )
    assert [f.id for f in i.issue_candidates] == [
        "issue.timing.uneven_rhythm",
        "issue.history.rhythm_less_steady",
    ]
    assert 1 <= len(i.priorities) <= 3 and [p.rank for p in i.priorities] == [1, 2]
    assert i.priorities[0].score >= i.priorities[1].score
    for p in i.priorities:
        assert p.score == sum(f.points for f in p.factors)
        outside = next(f for f in p.factors if f.name == "Outside evidence")
        assert outside.points == 0 and "None verified" in outside.detail
    history = next(p for p in i.priorities if p.finding_id == "issue.history.rhythm_less_steady")
    assert next(f for f in history.factors if f.name == "Seen across swims").points == 2
    assert {p.finding_id for p in i.priorities} <= {f.id for f in i.issue_candidates}


# ---------- structure ----------


def test_findings_are_unique_stable_and_round_trip():
    args = dict(context=SwimmerContext(goals=["stroke_consistency"]), history=[prior(result(EVEN))])
    a, b = (
        interpret(result(UNEVEN), "v", "a1", **args),
        interpret(result(UNEVEN), "v", "a1", **args),
    )
    ids = [f.id for f in a.observations + a.issue_candidates]
    assert len(ids) == len(set(ids))
    assert ids == [f.id for f in b.observations + b.issue_candidates]
    assert a.model_dump(exclude={"created_at"}) == b.model_dump(
        exclude={"created_at"}
    )  # deterministic
    back = Interpretation.model_validate(a.to_firestore())
    assert (
        back == a
        and back.interpretation_version == "1.0"
        and back.rules_version == interp.RULES_VERSION
    )
    assert (back.analysis_id, back.analysis_schema_version) == ("a1", "1.2")
    assert len(a.to_firestore().__str__()) < 60_000


def test_every_rule_is_documented_and_pending_rules_do_nothing():
    for r in interp.RULES:
        if r.active:
            assert r.requires and r.logic and r.suppressed_when
        else:
            assert r.needs_reference and r.rule_id.startswith("pending.")
    i = interpret(result(UNEVEN), "v")
    assert {r.rule_id for r in i.rules} == {r.rule_id for r in interp.RULES}
    assert sum(r.state == "pending_validation" for r in i.rules) == sum(
        not r.active for r in interp.RULES
    )
    assert FREESTYLE.stroke == "Freestyle"


def test_a_modest_rise_in_variation_between_two_short_clips_is_within_noise():
    # 2% then 13% looks like a change, but each value comes from seven cycles: the rule's
    # threshold (sampling error of both values plus timing resolution) is not passed.
    i = interpret(result(UNEVEN), "v", history=[prior(result(EVEN))])
    status = rule(i, "history.rhythm_less_steady")
    assert status.state == "not_triggered" and "could be noise" in status.reason
    assert [f.id for f in i.issue_candidates] == ["issue.timing.uneven_rhythm"]
