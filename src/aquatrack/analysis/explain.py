"""Optional rewording of feedback by a language model, and the checks that guard it.

The model is given only structured, already-validated text (no video, no name, no email, no
account id) and asked to reword each item for a swimmer. Its answer is never trusted:
`validate` checks it against a whitelist built from the feedback itself, and one failed
check throws the whole answer away. The deterministic text (`FeedbackItem.body`) is always
kept, so the page works the same with no model, a failed call or a rejected answer.

Off by default. Set AQUATRACK_LLM=claude (and install the `llm` extra, with credentials in
the environment) to switch it on. Nothing in the tests calls the API.
"""
# ruff: noqa: E501

import json
import logging
import os
import re
from typing import Protocol

from aquatrack import evidence
from aquatrack.contracts import ExplanationInfo, Feedback, FeedbackItem

log = logging.getLogger("aquatrack.explain")

DEFAULT_MODEL = "claude-opus-5-5"
MAX_CHARS = 900

SYSTEM = """You reword swimming feedback for an individual swimmer. You are given a list of items. Each item already contains everything that may be said: its text, its numbers, and the research claims it may mention.

Rules:
- Reword each item's text in plain, friendly English for a swimmer. Keep its meaning exactly.
- Use only numbers that appear in that item. Do not add, round, convert or combine numbers.
- Mention research only by the claim ids listed for that item, in "citations". Do not name any other study, author or year.
- Keep each item in its category. An "observation" describes a measurement and must not call anything a problem. A "focus" or "priority" is something to look at, never a confirmed fault. An "education" item is general information: it must not say or imply anything about this swimmer's own video or stroke. An "insufficient" item explains a limit.
- Do not promise results, mention injuries or health, give target angles or times, suggest breath-holding, or say a coach or any person reviewed the video.
- Return one entry per item id you reword. You may leave an item out; its original text is then used."""

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "citations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "text", "citations"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

BANNED = re.compile(
    r"guarantee|will (make|help) you (swim )?(faster|better)|will improve|coach (has |have )?(reviewed|watched|looked|checked)|"
    r"injur|diagnos|medical|ideal (angle|position|value)|optimal (angle|position)|should be (about |around |at least |under )?\d|"
    r"hold(ing)? your breath|breath[- ]hold|hypoxic|prevent",
    re.I,
)
# An observation may describe; these words turn it into a judgement.
JUDGING = re.compile(
    r"\b(problem|fault|flaw|weakness|mistake|incorrect|wrong|poor|bad|needs? (work|attention|fixing)|you should|too (high|low|much|little|slow|fast))\b",
    re.I,
)
# General information must not talk about this swimmer's own swimming.
PERSONAL = re.compile(
    r"\b(your (video|clip|swim|stroke|rhythm|body|head|arms?|legs?|pull|elbow|technique)|we (measured|saw|observed|found|noticed)|in this (video|clip)|you (tend|appear|seem|are|were) )",
    re.I,
)
CITATION = re.compile(
    r"\b([A-Z][a-zA-Z'-]+)(?: et al\.?| and [A-Z][a-zA-Z'-]+)?,? \(?(?:19|20)\d{2}\)?"
)
NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?")


class Rejected(ValueError):
    """The model's answer broke a rule. The reason is kept for the record, never shown."""


class ExplainError(RuntimeError):
    """The model could not be reached or declined."""


class Explainer(Protocol):
    model: str

    def explain(self, payload: dict) -> dict: ...


def build_payload(feedback: Feedback) -> dict:
    """What is sent to the model: structured feedback only. No identifiers of the swimmer,
    their video or their account, and none of the swimmer's free-text notes."""
    return {
        "swimmer": {
            "level": feedback.swim_level,
            "goals": feedback.goals_used,
            "main_goal": feedback.primary_goal,
        },
        "items": [
            {
                "id": item.id,
                "category": item.category,
                "title": item.title,
                "text": item.body,
                "why_it_may_matter": item.why_it_may_matter,
                "limitations": item.limitations[:4],
                "claims": [
                    {
                        "id": c,
                        "kind": evidence.CLAIMS[c].kind,
                        "statement": evidence.CLAIMS[c].statement,
                    }
                    for c in item.claim_ids
                ],
            }
            for item in feedback.items
        ],
    }


def _numbers(text: str) -> set[float]:
    return {round(float(n), 6) for n in NUMBER.findall(text)}


def allowed_numbers(item: FeedbackItem) -> set[float]:
    """Every number the item itself contains: its text, and its measurements."""
    text = " ".join(
        [item.title, item.body, item.why_it_may_matter, item.monitor, *item.limitations]
    )
    allowed = _numbers(text)
    for e in item.evidence:
        for v in (e.value, e.low, e.high, float(e.n_cycles)):
            if v is not None:
                allowed.add(round(float(v), 6))
        for s in e.samples:
            allowed |= {round(float(s.value), 6), round(float(s.t_s), 6)}
    return allowed


def validate(feedback: Feedback, response: object) -> dict[str, str]:
    """Check a model answer against the feedback it was asked to reword. Returns
    {item id: text} or raises `Rejected`. Any single violation rejects everything."""
    if not isinstance(response, dict) or not isinstance(response.get("items"), list):
        raise Rejected("not the requested structure")
    items = {item.id: item for item in feedback.items}
    surnames = {s.authors[0].split()[0]: s.id for s in evidence.SOURCES.values()}
    out: dict[str, str] = {}
    for entry in response["items"]:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("id"), str)
            or not isinstance(entry.get("text"), str)
        ):
            raise Rejected("malformed entry")
        item = items.get(entry["id"])
        if item is None:
            raise Rejected(f"unknown item id {entry['id']!r}: the model may not add findings")
        if entry["id"] in out:
            raise Rejected(f"item {entry['id']} answered twice")
        text = entry["text"].strip()
        if not text or len(text) > MAX_CHARS:
            raise Rejected(f"{item.id}: empty or over {MAX_CHARS} characters")
        extra = _numbers(text) - allowed_numbers(item)
        if extra:
            raise Rejected(f"{item.id}: numbers not in the item: {sorted(extra)}")
        citations = entry.get("citations") or []
        if not isinstance(citations, list) or any(c not in item.claim_ids for c in citations):
            raise Rejected(f"{item.id}: cites a claim that is not attached to it")
        own_sources = {evidence.CLAIMS[c].source_id for c in item.claim_ids}
        for name in CITATION.findall(text):
            if surnames.get(name) not in own_sources:
                raise Rejected(f"{item.id}: names a study that is not attached to it ({name})")
        if BANNED.search(text):
            raise Rejected(
                f"{item.id}: a claim that is never allowed ({BANNED.search(text).group(0)!r})"
            )
        if item.category in ("observation", "insufficient", "education") and JUDGING.search(text):
            raise Rejected(
                f"{item.id}: {item.category} worded as a judgement ({JUDGING.search(text).group(0)!r})"
            )
        if item.category == "education" and PERSONAL.search(text):
            raise Rejected(f"{item.id}: general information worded as a personal finding")
        if item.category in ("focus", "priority") and re.search(
            r"\b(confirmed|definitely|clearly a|is a (fault|flaw|problem))\b", text, re.I
        ):
            raise Rejected(f"{item.id}: a possible focus worded as a confirmed fault")
        out[item.id] = text
    return out


def explain_feedback(feedback: Feedback, explainer: Explainer | None) -> Feedback:
    """Add validated rewording to the feedback, or leave it exactly as it is. Never raises."""
    if explainer is None:
        return feedback
    try:
        texts = validate(feedback, explainer.explain(build_payload(feedback)))
    except Rejected as e:
        log.warning("model rewording rejected: %s", e)
        feedback.explanation = ExplanationInfo(
            source="template", model=explainer.model, note=f"Rewording rejected: {e}"
        )
        return feedback
    except Exception as e:  # unreachable API, refusal, bad JSON: the page must still work
        log.warning("model rewording unavailable: %s", type(e).__name__)
        feedback.explanation = ExplanationInfo(
            source="template",
            model=explainer.model,
            note=f"Rewording unavailable ({type(e).__name__}).",
        )
        return feedback
    for item in feedback.items:
        item.explained = texts.get(item.id, "")
    feedback.explanation = ExplanationInfo(source="llm", model=explainer.model)
    return feedback


class ClaudeExplainer:
    """Calls the Claude Messages API once per feedback with a JSON schema for the answer.
    Needs the `anthropic` package (`uv sync --extra llm`) and credentials in the
    environment. Every call costs money: it is only made when AQUATRACK_LLM=claude."""

    def __init__(self, model: str | None = None):
        import anthropic  # imported here so the app runs without the package

        self._anthropic = anthropic
        self._client = anthropic.Anthropic()
        self.model = model or os.environ.get("AQUATRACK_LLM_MODEL", DEFAULT_MODEL)

    def explain(self, payload: dict) -> dict:
        anthropic = self._anthropic
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM,
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": SCHEMA},
                },
                messages=[{"role": "user", "content": json.dumps(payload, sort_keys=True)}],
            )
        except anthropic.RateLimitError as e:
            raise ExplainError("rate limited") from e
        except anthropic.APIStatusError as e:
            raise ExplainError(f"API error {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise ExplainError("network error") from e
        if response.stop_reason != "end_turn":
            raise ExplainError(f"stopped: {response.stop_reason}")  # refusal, max_tokens, ...
        text = next((b.text for b in response.content if b.type == "text"), "")
        return json.loads(text)


def explainer_from_env() -> Explainer | None:
    """The configured explainer, or None (the default): no key, no call, no cost."""
    if os.environ.get("AQUATRACK_LLM", "").lower() != "claude":
        return None
    try:
        return ClaudeExplainer()
    except Exception as e:
        log.warning("language model not available: %s", type(e).__name__)
        return None
