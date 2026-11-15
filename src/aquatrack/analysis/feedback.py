"""Feedback: what to tell the swimmer, built from an Interpretation, their goals and the
evidence library. Deterministic; the text here is always shown as it is unless a language
model's rewording passes validation (see `explain`).

Five categories that are never mixed:

  observation   measured in this swimmer's video
  focus         a pattern in their own swimming that may deserve attention (not a fault)
  priority      a focus that is also ranked, at most three
  education     general information for a goal they chose. It is NOT about their video, is
                never called a weakness and never gets a priority.
  insufficient  what could not be determined, and what footage or information would help

Nothing here creates a finding. Observations, focus items and priorities come one-to-one
from the interpretation; goals only add education and decide order. Choosing a goal never
makes something measurable.
"""
# ruff: noqa: E501  (sentences shown to the swimmer are kept whole)

import hashlib
import json

from aquatrack import evidence
from aquatrack.analysis.interpretation import GOALS, RESOLUTION, TIMING_FRAMES
from aquatrack.contracts import (
    Checkpoint,
    Feedback,
    FeedbackItem,
    FeedbackReference,
    Finding,
    Interpretation,
)

MAX_CHECKPOINTS = 4
MIN_CYCLES_FOR_RHYTHM = 6

RECORDING_TIPS = [
    "Freestyle, filmed under water from the side, is what the analysis is built for.",
    "Keep the whole swimmer in the picture, head to feet, for the whole clip.",
    "Hold the camera level and side-on. Move it along with the swimmer or keep it still; avoid zooming, and avoid filming a swimmer who comes toward the camera or swims away from it.",
    "Film at least six full strokes of one arm (about 8 to 15 seconds). Longer is better for rhythm.",
    "Clear water and good light help; splashes, bubbles and other swimmers in front hide the body.",
    "For comparing two swims, film the same distance at the same effort from the same place.",
]

# Which library claims may explain why a rule's pattern is worth a look.
RULE_CLAIMS = {
    "timing.uneven_rhythm": ["no_single_ideal_coordination", "heuristic_rhythm_thresholds"],
    "history.rhythm_less_steady": ["no_single_ideal_coordination", "compare_like_with_like"],
}

# General information per goal: what research in the library says, what AquaTrack can look at
# for that goal today, and what it cannot. Shown only when the swimmer chose the goal.
GUIDES: dict[str, dict] = {
    "stroke_consistency": {
        "claims": [
            "no_single_ideal_coordination",
            "speed_variation_within_stroke_differs_by_level",
        ],
        "can": "From a side-view clip AquaTrack times each stroke cycle and reports how much the cycle time varies. With six or more cycles of one arm it can point to the cycles that were off your own rhythm.",
        "cannot": "It cannot measure how your speed changes inside each stroke, which is what the research on steadiness and skill level measured.",
    },
    "body_alignment": {
        "claims": ["trunk_incline_falls_with_speed", "head_position_changes_passive_drag"],
        "can": "AquaTrack measures the body line, the legs against the trunk line and the head against the trunk line in the picture, and compares them with your own earlier swims filmed the same way.",
        "cannot": "It does not judge these values as good or bad: its picture angles have not been checked against the measurements used in the research, and no target value has been verified.",
    },
    "arm_technique": {
        "claims": ["coordination_changes_with_pace", "coordination_mode_switches_with_speed"],
        "can": "AquaTrack shows pull depth and elbow bend for the arm nearer the camera, for information only.",
        "cannot": "It cannot measure the timing between your two arms (the far arm is hidden from the side), and the arm points are not yet reliable enough to find issues.",
    },
    "speed": {
        "claims": [
            "stroke_rate_and_length_change_with_race_pace",
            "performance_links_stroke_kinematics_and_energetics",
        ],
        "can": "AquaTrack measures your stroke rate in a clip.",
        "cannot": "It does not measure swim speed or distance per stroke, so it cannot say whether a stroke rate suits you or the distance.",
    },
    "endurance": {
        "claims": [
            "coordination_profiles_differ_and_change_with_fatigue",
            "speed_variation_within_stroke_differs_by_level",
        ],
        "can": "On a clip with at least nine cycles AquaTrack compares cycle time at the start and at the end.",
        "cannot": "A clip of a few seconds says nothing about fatigue over a longer swim.",
    },
    "breathing": {
        "claims": ["body_roll_asymmetry_not_shown_to_affect_performance"],
        "can": "Nothing yet.",
        "cannot": "Breathing and body roll cannot be measured from an underwater side view, so AquaTrack reports nothing about your breathing.",
    },
    "overall_freestyle": {
        "claims": ["no_single_ideal_coordination", "compare_like_with_like"],
        "can": "AquaTrack describes stroke timing and body position in a clip and follows how they change across your own comparable swims.",
        "cannot": "It does not compare you with other swimmers or with an ideal stroke.",
    },
}

# What would help, per kind of gap. Keys are prefixes of `Undetermined.key`.
HELP = {
    "camera_view": "A clip filmed side-on with the camera moving along with you, or held still at the side.",
    "camera_side": "A clip filmed from the side where one arm is clearly nearer the camera for the whole swim.",
    "cycle_count": "A clip where the first and last strokes are fully in view.",
    "cycle_time_change": "A longer clip: at least nine full cycles of one arm.",
    "limited.rhythm_variation": "A longer clip: at least six full cycles of one arm.",
    "rhythm_variation": "A longer clip: at least six full cycles of one arm.",
    "no_history": "Another clip of the same distance and effort, filmed the same way.",
    "no_goals": "Add goals on your profile if you want findings ordered by what matters to you.",
    "no_metrics": "Run the analysis again on this video.",
    "stroke_rate": "A side-view clip in which the swimmer stays fully visible for at least six strokes of one arm.",
}


def _cite(claim_ids: list[str]) -> str:
    """'(Zamparo et al., 2009)' style mentions for the sources behind some claims."""
    out = []
    for cid in claim_ids:
        src = evidence.source_of(evidence.CLAIMS[cid])
        if src:
            who = src.authors[0].split()[0] + (
                " et al."
                if len(src.authors) > 2
                else f" and {src.authors[1].split()[0]}"
                if len(src.authors) == 2
                else ""
            )
            out.append(f"{who}, {src.year}")
    return "; ".join(dict.fromkeys(out))


def _observation(f: Finding) -> FeedbackItem:
    return FeedbackItem(
        id=f"fb.{f.id}",
        category="observation",
        personal=True,
        title=f.title,
        body=f.description,
        finding_id=f.id,
        metric_keys=f.metric_keys,
        evidence=f.evidence,
        confidence="measured" if f.evidence_class == "measured" else "for_information",
        limitations=[*f.limitations, *f.withheld],
    )


def _focus(f: Finding) -> FeedbackItem:
    claims = [c for c in RULE_CLAIMS.get(f.rule_id, []) if c in evidence.CLAIMS]
    cited = [c for c in claims if evidence.CLAIMS[c].kind == "scientific_finding"]
    why = (
        "Research on swimming coordination argues that there is no single ideal pattern and that some variation is how swimmers adapt "
        f"({_cite(cited)}). So this is something to look at in the video, not a fault: check whether those moments were a breath, a turn or a change of pace. "
        "The cut-offs used to flag it are AquaTrack's own and have not been validated."
        if cited
        else "No verified research backs a judgement here. It is flagged so you can look at those moments yourself."
    )
    return FeedbackItem(
        id=f"fb.{f.id}",
        category="focus",
        personal=True,
        title=f.title,
        body=f.description,
        why_it_may_matter=why,
        finding_id=f.id,
        metric_keys=f.metric_keys,
        evidence=f.evidence,
        claim_ids=claims,
        goal_keys=[k for k, label in GOALS.items() if label in f.context_used],
        confidence="measured",
        limitations=[*f.limitations, *f.withheld],
    )


def _education(goal: str, main: bool) -> FeedbackItem:
    guide = GUIDES[goal]
    claims = [evidence.CLAIMS[c] for c in guide["claims"]]
    said = " ".join(
        f"{c.statement} ({_cite([c.id])})" if c.source_id else c.statement for c in claims
    )
    return FeedbackItem(
        id=f"fb.education.{goal}",
        category="education",
        personal=False,
        title=f"About {GOALS[goal]}" + (" (your main goal)" if main else ""),
        body=f"General information, not a finding about your swimming. {said} What AquaTrack can look at today: {guide['can']} What it cannot: {guide['cannot']}",
        claim_ids=[c.id for c in claims],
        goal_keys=[goal],
        confidence="general",
        limitations=[*dict.fromkeys(limit for c in claims for limit in c.limitations[:2])],
    )


def _checkpoints(i: Interpretation, items: list[FeedbackItem]) -> list[Checkpoint]:
    out: list[Checkpoint] = []
    undetermined = {u.key for u in i.undetermined}
    measured = [x for x in items if x.category == "observation" and x.confidence == "measured"]
    tempo = next(
        (e for x in items for e in x.evidence if e.metric_key == "cycle_duration" and e.value), None
    )

    for item in items:
        if item.category in ("focus", "priority") and item.finding_id.startswith("issue."):
            out.append(
                Checkpoint(
                    id=f"cp.recurs.{item.finding_id}",
                    title="See whether this pattern shows up again",
                    related_item_id=item.id,
                    metric_keys=item.metric_keys,
                    what_to_film="The same distance at the same effort, from the same side-on position.",
                    minimum=f"At least {MIN_CYCLES_FOR_RHYTHM} full cycles of one arm.",
                    compare_with="This swim.",
                    what_counts_as_a_change="The same pattern in a second comparable swim is what turns it into a priority. One clip without it does not show it is gone.",
                    limitations=["A single practice session is not expected to change it."],
                )
            )
    if "camera_view" in undetermined or "camera_side" in undetermined or not i.observations:
        out.append(
            Checkpoint(
                id="cp.side_view",
                title="Film side-on with a steady view",
                metric_keys=["body_line_angle", "leg_line_angle", "head_height"],
                what_to_film="Under water from the side, the camera level and either moving along with you or held still. Keep your whole body in the picture.",
                minimum=f"At least {MIN_CYCLES_FOR_RHYTHM} full cycles of one arm.",
                limitations=[
                    "Better footage makes more measurable; it does not guarantee that every measurement will pass its checks."
                ],
            )
        )
    cycles = max(
        (e.n_cycles for x in items for e in x.evidence if e.metric_key == "cycle_duration"),
        default=0,
    )
    if i.observations and cycles < MIN_CYCLES_FOR_RHYTHM:
        seconds = (
            f" (about {round((MIN_CYCLES_FOR_RHYTHM + 1) * tempo.value)} seconds at this tempo)"
            if tempo
            else ""
        )
        out.append(
            Checkpoint(
                id="cp.longer_clip",
                title="Film a longer stretch to look at rhythm",
                metric_keys=["cycle_duration", "rhythm_variation"],
                what_to_film="One continuous stretch of swimming, side-on, without a turn in it.",
                minimum=f"At least {MIN_CYCLES_FOR_RHYTHM} full cycles of one arm{seconds}. This clip had {cycles}.",
                limitations=["With fewer cycles a single odd stroke looks like a pattern."],
            )
        )
    if i.baseline and measured:
        keys = [
            k
            for x in measured
            for k in x.metric_keys
            if k in RESOLUTION or k in ("cycle_duration", "stroke_rate")
        ]
        out.append(
            Checkpoint(
                id="cp.repeat_same_conditions",
                title="Film the same swim again to see what changes",
                metric_keys=list(dict.fromkeys(keys)),
                what_to_film="The same stroke and distance at the same effort, from the same place and angle as this clip.",
                compare_with="This swim, which is your baseline.",
                what_counts_as_a_change=f"A difference of more than about {2 * RESOLUTION['body_line_angle']:.0f} degrees in body or leg line, {2 * RESOLUTION['head_height']:.2f} trunk lengths in head position, or {TIMING_FRAMES} video frames in cycle time. Smaller differences are within measurement noise.",
                limitations=[
                    "A difference shows that something changed, not why, and not whether it is better.",
                    "A sprint and an easy swim are not compared with each other.",
                ],
            )
        )
    return out[:MAX_CHECKPOINTS]


def build_feedback(i: Interpretation, interpretation_id: str = "") -> Feedback:
    """Feedback for one interpretation. The swimmer's goals and level are the ones recorded
    in the interpretation's context, so the two can never disagree."""
    goals = [g for g in i.context.goals if g in GUIDES]
    by_finding = {f.id: f for f in i.issue_candidates}
    ranked = {p.finding_id: p for p in i.priorities}

    items: list[FeedbackItem] = []
    for p in i.priorities:  # ranked first
        item = _focus(by_finding[p.finding_id])
        item.category, item.rank, item.factors = "priority", p.rank, p.factors
        item.id = f"fb.priority.{p.finding_id}"
        item.monitor = (
            "Whether the same pattern shows up in your next comparable swim (see the checkpoints)."
        )
        items.append(item)
    items += [_focus(f) for f in i.issue_candidates if f.id not in ranked]
    items += [_observation(f) for f in i.observations]
    # Education: only for goals the swimmer chose, main goal first. Never ranked.
    ordered = sorted(goals, key=lambda g: (g != i.context.primary_goal, goals.index(g)))
    items += [_education(g, g == i.context.primary_goal) for g in ordered]
    for u in i.undetermined:
        helps = next((text for key, text in HELP.items() if u.key.startswith(key)), "")
        items.append(
            FeedbackItem(
                id=f"fb.insufficient.{u.key}",
                category="insufficient",
                personal=False,
                title=u.title,
                body=u.reason + (f" What would help: {helps}" if helps else ""),
                confidence="none",
            )
        )

    used = [c for item in items for c in item.claim_ids]
    sources = {}
    for cid in used:
        src = evidence.source_of(evidence.CLAIMS[cid])
        if src:
            sources[src.id] = FeedbackReference(
                source_id=src.id,
                citation=src.citation,
                url=src.url,
                kind=src.kind,
                population=src.population,
                read=src.read,
            )
    count = {
        c: sum(x.category == c for x in items)
        for c in ("observation", "focus", "priority", "education")
    }
    return Feedback(
        evidence_version=evidence.EVIDENCE_VERSION,
        rules_version=i.rules_version,
        interpretation_version=i.interpretation_version,
        video_id=i.video_id,
        analysis_id=i.analysis_id,
        interpretation_id=interpretation_id,
        goals_used=goals,
        primary_goal=i.context.primary_goal,
        swim_level=i.context.swim_level,
        items=items,
        checkpoints=_checkpoints(i, items),
        references=list(sources.values()),
        recording_tips=RECORDING_TIPS
        if (
            not i.observations
            or any(u.key in ("camera_view", "camera_side") for u in i.undetermined)
        )
        else [],
        summary=f"{count['observation']} observation{'s' if count['observation'] != 1 else ''} from your video, "
        f"{count['focus'] + count['priority']} to look at, {count['priority']} ranked as a priority, "
        f"{count['education']} general note{'s' if count['education'] != 1 else ''} for your goals.",
    )


def feedback_id(basis: str, feedback: Feedback) -> str:
    """An id from what the feedback was built from: `basis` (the interpretation's content),
    the evidence and feedback versions, the goals and the explanation source. The same
    inputs always give the same id, so regenerating does not pile up copies and never
    replaces a different one."""
    key = json.dumps(
        [
            basis,
            feedback.feedback_version,
            feedback.evidence_version,
            feedback.goals_used,
            feedback.primary_goal,
            feedback.explanation.source,
            feedback.explanation.model,
        ],
        sort_keys=True,
    )
    return hashlib.sha256(key.encode()).hexdigest()[:20]
