"""Feedback, the evidence library and the language-model guard. Results come from the
synthetic swimmer and every 'earlier swim' is a labelled fixture; the model is always a
mock. None of this is evidence that the feedback is effective for real swimmers."""

import json
import re

import pytest
from test_interpretation import EVEN, UNEVEN, WILD, prior, result

from aquatrack import evidence
from aquatrack.analysis import explain
from aquatrack.analysis.explain import Rejected, build_payload, explain_feedback, validate
from aquatrack.analysis.feedback import GUIDES, build_feedback, feedback_id
from aquatrack.analysis.interpretation import GOALS, SwimmerContext, interpret
from aquatrack.contracts import Feedback, MetricStatus


def feedback(times=EVEN, goals=(), primary=None, history=(), level=None, **kw) -> Feedback:
    ctx = SwimmerContext(swim_level=level, goals=list(goals), primary_goal=primary)
    r = kw.pop("r", None) or result(times)
    return build_feedback(interpret(r, "v", "a1", ctx, list(history)), "i1")


def of(f: Feedback, category: str):
    return [i for i in f.items if i.category == category]


# ---------- evidence library ----------


def test_every_source_has_a_checked_record_and_every_claim_a_kind_and_limits():
    assert len(evidence.SOURCES) >= 8
    for s in evidence.SOURCES.values():
        assert re.fullmatch(r"10\.\d{4,9}/\S+", s.doi) and s.url == f"https://doi.org/{s.doi}"
        assert s.title and s.authors and 1970 < s.year <= 2026 and s.journal and s.pmid.isdigit()
        assert s.population and s.methods and s.verified_on and s.read == "abstract"
    for c in evidence.CLAIMS.values():
        assert c.statement and c.context and c.applicability and c.limitations
        if c.kind in ("scientific_finding", "research_supported"):
            assert c.source_id in evidence.SOURCES  # traceable to a verified source
        else:
            assert c.source_id is None  # our own choices are never dressed up as research
    kinds = {c.kind for c in evidence.CLAIMS.values()}
    assert kinds == {
        "scientific_finding",
        "research_supported",
        "engineering_heuristic",
        "unverified_hypothesis",
    }


def test_claims_never_state_a_target_value_for_an_individual():
    target = re.compile(
        r"should be|must be|ideal (angle|value|rate)|optimal|aim for|\\d+ ?degrees", re.I
    )
    for c in evidence.CLAIMS.values():
        if c.kind != "engineering_heuristic":  # our own rule states its own cut-offs
            assert not target.search(c.statement), c.id
    assert all(set(g["claims"]) <= set(evidence.CLAIMS) for g in GUIDES.values())
    assert set(GUIDES) == set(GOALS)  # every goal a swimmer can pick has general information


# ---------- categories ----------


def test_observations_stay_observations_and_nothing_is_invented_for_a_clean_swim():
    f = feedback(EVEN)
    assert of(f, "priority") == [] and of(f, "focus") == [] and of(f, "education") == []
    obs = of(f, "observation")
    assert len(obs) >= 4 and all(i.personal and i.finding_id.startswith("obs.") for i in obs)
    assert all(
        i.claim_ids == [] and not i.why_it_may_matter for i in obs
    )  # no research pinned on a measurement
    assert f.references == [] and f.goals_used == []
    assert f.evidence_version == evidence.EVIDENCE_VERSION and f.interpretation_id == "i1"


def test_a_goal_adds_general_information_and_never_a_finding_or_priority():
    plain, with_goals = (
        feedback(EVEN),
        feedback(EVEN, goals=["breathing", "body_alignment"], primary="body_alignment"),
    )
    personal = lambda f: [(i.category, i.finding_id, i.body) for i in f.items if i.personal]  # noqa: E731
    assert personal(plain) == personal(
        with_goals
    )  # goals changed nothing that is about the swimmer
    edu = of(with_goals, "education")
    assert [i.goal_keys for i in edu] == [["body_alignment"], ["breathing"]]  # main goal first
    assert "(your main goal)" in edu[0].title
    for i in edu:
        assert not i.personal and i.confidence == "general" and i.rank is None and not i.evidence
        assert i.body.startswith("General information, not a finding about your swimming.")
        assert i.claim_ids and i.limitations
    assert of(with_goals, "priority") == []
    breathing = edu[1]
    assert (
        "cannot be measured" in breathing.body
        and "reports nothing about your breathing" in breathing.body
    )
    assert {r.source_id for r in with_goals.references} == {
        "zamparo2009",
        "cortesi2015",
        "psycharakis2010",
    }
    assert all(r.url.startswith("https://doi.org/10.") for r in with_goals.references)


def test_a_focus_explains_why_it_may_matter_with_its_source_and_stays_unconfirmed():
    f = feedback(UNEVEN)
    (focus,) = of(f, "focus")
    assert focus.finding_id == "issue.timing.uneven_rhythm" and of(f, "priority") == []
    assert (
        "Seifert et al., 2014" in focus.why_it_may_matter
        and "not a fault" in focus.why_it_may_matter
    )
    assert "AquaTrack's own" in focus.why_it_may_matter  # the thresholds are ours, and it says so
    assert set(focus.claim_ids) == {"no_single_ideal_coordination", "heuristic_rhythm_thresholds"}
    assert [r.source_id for r in f.references] == ["seifert2014"]
    assert any(e.label == "Cycles off the rhythm" and len(e.samples) == 3 for e in focus.evidence)


def test_priorities_need_a_matching_goal_or_history_and_are_capped_and_ranked():
    unrelated = feedback(UNEVEN, goals=["breathing"])
    assert of(unrelated, "priority") == [] and len(of(unrelated, "focus")) == 1
    matched = feedback(
        WILD,
        goals=["stroke_consistency", "speed"],
        primary="stroke_consistency",
        history=[prior(result(EVEN), "e1"), prior(result(EVEN), "e2")],
    )
    pri = of(matched, "priority")
    assert 1 <= len(pri) <= 3 and [p.rank for p in pri] == list(range(1, len(pri) + 1))
    assert all(p.monitor and p.factors and p.why_it_may_matter for p in pri)
    assert any(x.name == "Your goals" and x.points == 3 for x in pri[0].factors)  # main goal
    assert of(matched, "focus") == []  # ranked ones are not listed twice
    assert (
        matched.goals_used == ["stroke_consistency", "speed"]
        and matched.primary_goal == "stroke_consistency"
    )


def test_limited_and_unavailable_measurements_never_become_recommendations():
    r = result(UNEVEN)
    for m in r.metrics:
        if m.key in ("rhythm_variation", "body_line_angle"):
            m.status, m.reason = MetricStatus.LIMITED, "Only 3 stroke cycles."
    f = feedback(r=r, goals=["stroke_consistency", "body_alignment"])
    assert of(f, "focus") == [] and of(f, "priority") == []
    assert any(i.confidence == "for_information" for i in of(f, "observation"))

    for m in r.metrics:
        m.status, m.value, m.samples, m.reason = (
            MetricStatus.UNAVAILABLE,
            None,
            [],
            "The swimmer could not be followed reliably enough in this clip.",
        )
    f = feedback(r=r, goals=["stroke_consistency"])
    assert of(f, "observation") == [] and of(f, "focus") == [] and of(f, "priority") == []
    assert len(of(f, "education")) == 1 and f.recording_tips  # still useful: tips and general notes
    assert any("What would help:" in i.body for i in of(f, "insufficient"))
    assert [c.id for c in f.checkpoints] == ["cp.side_view"]


def test_missing_profile_and_goals_are_stated_not_filled_in():
    f = build_feedback(interpret(result(EVEN), "v"), "i1")
    assert f.goals_used == [] and f.swim_level is None and of(f, "education") == []
    gap = next(i for i in of(f, "insufficient") if i.id.endswith("no_goals"))
    assert "Add goals on your profile" in gap.body


# ---------- checkpoints ----------


def test_checkpoints_follow_the_evidence_and_promise_nothing():
    base = feedback(EVEN)
    repeat = next(c for c in base.checkpoints if c.id == "cp.repeat_same_conditions")
    assert (
        "baseline" in repeat.compare_with
        and "within measurement noise" in repeat.what_counts_as_a_change
    )
    assert any("not why" in text for text in repeat.limitations)
    assert not any(c.id == "cp.longer_clip" for c in base.checkpoints)  # seven cycles is enough

    r = result(EVEN)
    for m in r.metrics:
        if m.key in ("cycle_duration", "stroke_rate", "rhythm_variation"):
            m.n_cycles = 3
    short = feedback(r=r)
    longer = next(c for c in short.checkpoints if c.id == "cp.longer_clip")
    assert "At least 6 full cycles" in longer.minimum and "This clip had 3" in longer.minimum

    flagged = feedback(UNEVEN)
    recurs = next(c for c in flagged.checkpoints if c.id.startswith("cp.recurs."))
    assert recurs.related_item_id == of(flagged, "focus")[0].id
    assert "single practice session is not expected" in recurs.limitations[0]
    text = json.dumps(
        [c.model_dump() for f in (base, short, flagged) for c in f.checkpoints]
    ).lower()
    assert not re.search(
        r"\b(will improve|guarantee|faster|drill|sets? of|times? per week)\b", text
    )
    assert all(len(f.checkpoints) <= 4 for f in (base, short, flagged))


# ---------- the language-model guard (mocked; no API call is ever made) ----------


class Mock:
    model = "mock-model"

    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.payloads = answer, error, []

    def explain(self, payload):
        self.payloads.append(payload)
        if self.error:
            raise self.error
        return self.answer(payload) if callable(self.answer) else self.answer


def reword(payload, **overrides):
    """A well-behaved model: the same text with a friendly lead-in, the same claims. Items
    whose text is too long to carry the lead-in are left out, which is allowed."""
    out = []
    for i in payload["items"]:
        if i["id"] in overrides:
            text = overrides[i["id"]]
        elif len(i["text"]) < 860:
            text = "Here is what this means. " + i["text"]
        else:
            continue
        out.append({"id": i["id"], "text": text, "citations": [c["id"] for c in i["claims"]]})
    return {"items": out}


def test_a_faithful_rewording_is_accepted_and_the_original_text_is_kept():
    f = feedback(UNEVEN, goals=["stroke_consistency"])
    originals = {i.id: i.body for i in f.items}
    mock = Mock(reword)
    out = explain_feedback(f, mock)
    assert out.explanation.source == "llm" and out.explanation.model == "mock-model"
    assert any(i.explained.startswith("Here is what this means.") for i in out.items)
    assert {i.id: i.body for i in out.items} == originals  # body is never replaced
    assert feedback_id("i1", out) != feedback_id(
        "i1", feedback(UNEVEN, goals=["stroke_consistency"])
    )


def test_the_model_is_sent_structured_feedback_and_nothing_that_identifies_the_swimmer():
    f = feedback(UNEVEN, goals=["stroke_consistency"], level="hobby")
    payload = build_payload(f)
    assert set(payload) == {"swimmer", "items"} and payload["swimmer"] == {
        "level": "hobby",
        "goals": ["stroke_consistency"],
        "main_goal": None,
    }
    text = json.dumps(payload)
    for private in (
        "uid",
        "email",
        "video_id",
        "analysis_id",
        '"v"',
        "a1",
        "i1",
        "weak_note",
        "storage",
    ):
        assert private not in text
    assert all(
        set(i) == {"id", "category", "title", "text", "why_it_may_matter", "limitations", "claims"}
        for i in payload["items"]
    )


@pytest.mark.parametrize(
    ("item", "text", "why"),
    [
        (
            "fb.obs.stroke_tempo",
            "Your stroke rate was 52.5 cycles per minute.",
            "numbers not in the item",
        ),
        (
            "fb.obs.stroke_tempo",
            "You took 50.0 cycles per minute, about 12 percent above average.",
            "numbers not in the item",
        ),
        (
            "fb.obs.leg_line",
            "Your legs sit at this angle, which is a problem you should fix.",
            "worded as a judgement",
        ),
        (
            "fb.obs.head",
            "As Smith et al. (2019) showed, head position matters.",
            "numbers not in the item",
        ),
        (
            "fb.obs.rhythm",
            "Maglischo and Counsilman found that rhythm matters.",
            "",
        ),  # no year: allowed words only? see below
        (
            "fb.priority.issue.timing.uneven_rhythm",
            "This is definitely a fault in your stroke.",
            "confirmed fault",
        ),
        (
            "fb.priority.issue.timing.uneven_rhythm",
            "Fixing this will make you faster.",
            "never allowed",
        ),
        (
            "fb.priority.issue.timing.uneven_rhythm",
            "A coach has reviewed your video and agrees.",
            "never allowed",
        ),
        (
            "fb.priority.issue.timing.uneven_rhythm",
            "This can prevent shoulder injury.",
            "never allowed",
        ),
        (
            "fb.education.stroke_consistency",
            "Your stroke shows this kind of variation.",
            "personal finding",
        ),
        ("fb.education.stroke_consistency", "We measured this in your video.", "personal finding"),
    ],
)
def test_unsupported_claims_reject_the_whole_answer(item, text, why):
    f = feedback(UNEVEN, goals=["stroke_consistency"])
    answer = reword(build_payload(f), **{item: text})
    if not why:  # a named study without a year is still words, not a checkable citation
        assert item in validate(f, answer)
        return
    with pytest.raises(Rejected, match=why):
        validate(f, answer)
    out = explain_feedback(f, Mock(answer))
    assert out.explanation.source == "template" and "rejected" in out.explanation.note
    assert all(i.explained == "" for i in out.items)  # nothing from a rejected answer is used


def test_fabricated_and_misplaced_citations_are_rejected():
    f = feedback(UNEVEN, goals=["body_alignment"])
    payload = build_payload(f)
    base = reword(payload)
    for entry in base["items"]:
        if entry["id"] == "fb.obs.head":
            entry["citations"] = [
                "head_position_changes_passive_drag"
            ]  # a real claim, not attached to this item
    with pytest.raises(Rejected, match="not attached"):
        validate(f, base)
    invented = reword(payload)
    invented["items"][0]["citations"] = ["made_up_claim_2021"]
    with pytest.raises(Rejected, match="not attached"):
        validate(f, invented)
    # Naming a library study on an item it does not belong to (the year is not in the item either).
    named = reword(
        payload,
        **{"fb.obs.leg_line": "As Zamparo et al., 2009 found, a flatter body has less drag."},
    )
    with pytest.raises(Rejected):
        validate(f, named)


def test_the_model_cannot_add_change_or_duplicate_items():
    f = feedback(EVEN)
    extra = reword(build_payload(f))
    extra["items"].append(
        {"id": "fb.issue.dropped_elbow", "text": "Your elbow drops.", "citations": []}
    )
    with pytest.raises(Rejected, match="may not add findings"):
        validate(f, extra)
    twice = reword(build_payload(f))
    twice["items"].append(dict(twice["items"][0]))
    with pytest.raises(Rejected, match="answered twice"):
        validate(f, twice)
    for bad in (
        None,
        "text",
        {"items": "x"},
        {"items": [{"id": 1}]},
        {"items": [{"id": "fb.obs.head", "text": "", "citations": []}]},
    ):
        with pytest.raises(Rejected):
            validate(f, bad)


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("network down"),
        explain.ExplainError("stopped: refusal"),
        json.JSONDecodeError("bad", "", 0),
    ],
)
def test_api_failure_falls_back_to_the_deterministic_text(error):
    f = feedback(UNEVEN, goals=["stroke_consistency"])
    before = f.model_dump(exclude={"explanation"})
    out = explain_feedback(f, Mock(error=error))
    assert out.explanation.source == "template" and "unavailable" in out.explanation.note
    assert out.model_dump(exclude={"explanation"}) == before  # the feedback itself is untouched
    assert all(i.body for i in out.items)


def test_no_explainer_is_configured_by_default_and_none_means_no_call(monkeypatch):
    monkeypatch.delenv("AQUATRACK_LLM", raising=False)
    assert explain.explainer_from_env() is None
    f = feedback(EVEN)
    assert explain_feedback(f, None).explanation.source == "template"


# ---------- identity, versions ----------


def test_the_same_inputs_give_the_same_feedback_and_id():
    a, b = (
        feedback(UNEVEN, goals=["stroke_consistency"]),
        feedback(UNEVEN, goals=["stroke_consistency"]),
    )
    assert a.model_dump(exclude={"created_at"}) == b.model_dump(exclude={"created_at"})
    assert feedback_id("i1", a) == feedback_id("i1", b)
    assert feedback_id("i1", a) != feedback_id("i2", a)
    assert feedback_id("i1", a) != feedback_id("i1", feedback(UNEVEN, goals=["speed"]))
    back = Feedback.model_validate(a.to_firestore())
    assert back == a and back.feedback_version == "1.0"
    ids = [i.id for i in a.items]
    assert len(ids) == len(set(ids))
