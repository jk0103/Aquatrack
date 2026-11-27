"""Hybrid advice: a model interprets the motion profile, deterministic code checks it.

    AnalysisResult + cleaned pose -> motion profile (motion_profile.py, deterministic)
        -> one model call: movement patterns, hypotheses, things to try (this file)
        -> checks: every piece of the answer is verified against the profile; pieces that
           fail are dropped one by one, the rest is kept
        -> Advice document (contracts.Advice), stored once per set of inputs

The Python analysis stays the authority for every measurement. The model may interpret the
numbers; it may not add, change or contradict them. Its confidence is recorded and counts
for nothing in the checks.

Off unless AQUATRACK_ADVICE_PROVIDER=openai and OPENAI_API_KEY are set in the backend's
environment (each analysed video then makes one billed call). Without it, or when the call
fails or nothing passes the checks, the Advice document has source "deterministic" and the
app shows the existing Feedback. Only the profile is sent: no video, frame, name, e-mail
or free-text note. Requests use `store=False`.

Evidence for this design, and its limits: docs/ADVICE.md.
"""

import json
import logging
import os
import re
import threading
from datetime import UTC, datetime
from typing import Protocol

from aquatrack import __version__
from aquatrack.analysis import motion_profile
from aquatrack.contracts import (
    Advice,
    AdviceObservation,
    AdvicePractice,
    AdviceRejected,
    AdviceSuggestion,
    AnalysisResult,
)
from aquatrack.training import library

log = logging.getLogger("aquatrack.advice")

PROMPT_VERSION = "2026.11-3"
DEFAULT_MODEL = "gpt-6.2-astra"
DEFAULT_REASONING = "high"
DEFAULT_MAX_OUTPUT_TOKENS = 40000  # includes reasoning tokens
DEFAULT_TIMEOUT_S = 300
DEFAULT_MAX_CALLS_PER_DAY = 100
MAX_SUGGESTIONS = 3
MIN_CYCLES_FOR_PATTERN = 2
MIN_USABLE_SHARE = 0.6  # of frames, for the joints a suggestion is about
# Below this many trusted cycles of the followed arm a pattern is a small sample: it is kept
# but marked tentative. Engineering choice (the rhythm rule needs 6; a trend needs at least 4).
MIN_CYCLES_FOR_FIRM = 4
# A timing difference smaller than this many video frames is at the limit of what the stroke
# events can resolve (an event is placed to the nearest frame, at both ends of an interval).
MIN_FRAMES_FOR_TIMING = 3
TIMING_FEATURES = (
    "cycle_duration_s",
    "front_phase_s",
    "catch_to_mid_pull_s",
    "mid_pull_to_exit_s",
    "exit_to_next_reach_s",
)
CATEGORIES = ["timing", "arm_path", "body_alignment", "legs", "head", "breathing", "other"]
CATEGORY_JOINTS = {
    "arm_path": ("elbow", "wrist"),
    "legs": ("knee", "ankle"),
    "body_alignment": ("shoulder", "hip"),
}
# Free-text sections of the profile an evidence reference may point into.
PROFILE_ROOTS = ("motion", "stroke_cycles", "tracking_quality", "clip", "session")
NUMBER = re.compile(r"(?<![A-Za-z_])-?\d+(?:\.\d+)?")
UNSAFE = re.compile(r"breath[- ]?hold|hold(ing)? (your|the) breath|hypoxic|no[- ]breath", re.I)
PROMISE = re.compile(r"\b(will|guarantee[ds]?) (make you|be) (faster|quicker)|guaranteed?\b", re.I)
IDEAL = re.compile(
    r"\b(ideal|optimal|correct|proper|should be)\b[^.]{0,40}\b(angle|degrees?|°)", re.I
)

SYSTEM = """You are an expert swimming-technique analyst. You are given what a \
pose-estimation pipeline measured from one freestyle clip filmed underwater from the side: \
the metrics and a motion profile. Nobody has interpreted it for you. Work out how this \
swimmer moves and what, if anything, they could work on.

How to work:
- Read the motion as movement: how the arm travels through reach, catch, pull and exit, how \
the joints relate (shoulder, elbow, wrist; hip, knee, ankle; head and body line), and above \
all what changes or repeats from one stroke cycle to the next.
- First judge the data. Where the pose data cannot be trusted (missing, interpolated or \
dropped points, untrusted cycles, camera effects), say so in data_quality and do not build \
on those parts. Anything that could equally be the camera, the tracker or one odd sample \
belongs in data_quality, not in suggestions.
- observations: what the measurements show, stated plainly with the numbers.
- consistent: what the swimmer repeats well. A steady rhythm or a repeatable pull goes \
here. It is never a suggestion and never a problem.
- suggestions: at most three, the most useful first. Each is a coaching hypothesis about \
something the swimmer does, seen in at least two stroke cycles or as a steady trend over \
several, and larger than the stated measurement uncertainty. Give: what was noticed, why it \
may matter (as a possibility, not an established cause), something concrete to try in the \
water, a drill, and what to look for in the next video. Choose drill_id from the drill list \
when one fits this pattern, otherwise leave it empty; drill_note says how to do that drill \
for this swimmer.
- Small samples. Count the trusted stroke cycles of the followed arm. With fewer than four, \
a pattern is a first indication, not an established habit: say so in "noticed" and word the \
suggestion as something to check on a longer clip. Stroke events are placed to the nearest \
video frame (see uncertainty.timing_resolution_s), so a timing difference of only a frame or \
two between cycles is not a difference; do not build a suggestion on it.
- Exploratory values. The input lists, under motion.exploratory, per-cycle features and \
sample fields that are raw leg positions and not verified measurements (the kick is faster \
than the path samples and has never been checked against video). You may point to a \
repeated pattern in them as something for the swimmer to look at in their video, but say in \
"noticed" that it comes from unverified leg tracking, never call it a fault, and put any \
suggestion that rests on measured values first.
- Finding nothing to suggest is a correct answer for a steady swimmer or unusable data. Do \
not invent a suggestion to be helpful, and do not withhold a pattern the data show clearly.

Hard limits:
- Every number you write must appear in the input, in every field including try_this, \
drill_note and check_next_time. Do not compute new numbers.
- Do not describe footage: you were given measurements, not video.
- Do not reason from a metric whose status is "unavailable", or about joints the tracking \
section shows as mostly unusable.
- Do not assume an ideal angle or position. Compare the swimmer with themselves.
- evidence_refs: metric keys, or paths into the input such as \
"motion.cycle_to_cycle.elbow_angle_at_mid_pull_deg".
- No breath-holding or hypoxic work and no promises about performance."""


def _obj(**props) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(props),
        "properties": props,
    }


_STR = {"type": "string"}
_REFS = {"type": "array", "items": _STR}
_TIMES = {"type": "array", "items": {"type": "number"}}
_STATEMENT = _obj(statement=_STR, evidence_refs=_REFS, times_s=_TIMES)
SCHEMA = _obj(
    data_quality={"type": "array", "items": _obj(problem=_STR, affects=_STR)},
    observations={"type": "array", "items": _STATEMENT},
    consistent={"type": "array", "items": _STATEMENT},
    suggestions={
        "type": "array",
        "items": _obj(
            title=_STR,
            category={"type": "string", "enum": CATEGORIES},
            noticed=_STR,
            why_it_may_matter=_STR,
            try_this=_STR,
            drill_id=_STR,
            drill_note=_STR,
            check_next_time=_STR,
            confidence={"type": "string", "enum": ["low", "medium", "high"]},
            cycles_supporting={"type": "integer"},
            evidence_refs=_REFS,
            times_s=_TIMES,
        ),
    },
    summary=_STR,
)


class AdviceError(Exception):
    """The model could not be used for this advice. Never shown to the swimmer."""


class Interpreter(Protocol):
    model: str
    reasoning: str

    def interpret(self, payload: dict) -> tuple[dict, dict[str, int]]:
        """The model's answer (SCHEMA) and its token usage."""
        ...


class OpenAIInterpreter:
    """One Responses API call per interpretation: strict JSON schema, high reasoning effort,
    no automatic retry (a failed call falls back to the deterministic advice instead of
    being repeated), `store=False`. The key is read by the SDK from the environment and is
    never logged, stored or returned."""

    def __init__(self, model: str | None = None, client=None):
        import openai  # imported here so the app runs without the package

        self._openai = openai
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise AdviceError("OPENAI_API_KEY is not set")
            client = openai.OpenAI(timeout=DEFAULT_TIMEOUT_S, max_retries=0)
        self._client = client
        self.model = model or os.environ.get("AQUATRACK_ADVICE_MODEL") or DEFAULT_MODEL
        self.reasoning = os.environ.get("AQUATRACK_ADVICE_REASONING") or DEFAULT_REASONING
        self.max_output_tokens = int(
            os.environ.get("AQUATRACK_ADVICE_MAX_OUTPUT_TOKENS") or DEFAULT_MAX_OUTPUT_TOKENS
        )
        self.max_calls_per_day = int(
            os.environ.get("AQUATRACK_ADVICE_MAX_CALLS_PER_DAY") or DEFAULT_MAX_CALLS_PER_DAY
        )
        self._day, self._calls = "", 0
        self._lock = threading.Lock()

    def request(self, payload: dict) -> dict:
        return {
            "model": self.model,
            "instructions": SYSTEM,
            "input": json.dumps(payload, separators=(",", ":")),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "motion_advice",
                    "schema": SCHEMA,
                    "strict": True,
                }
            },
            "reasoning": {"effort": self.reasoning},
            "max_output_tokens": self.max_output_tokens,
            "store": False,
        }

    def interpret(self, payload: dict) -> tuple[dict, dict[str, int]]:
        openai = self._openai
        today = datetime.now(UTC).date().isoformat()
        with self._lock:  # a ceiling on attempts per process per day
            if today != self._day:
                self._day, self._calls = today, 0
            if self._calls >= self.max_calls_per_day:
                raise AdviceError("daily call limit reached")
            self._calls += 1
        try:
            response = self._client.responses.create(**self.request(payload))
        except openai.APITimeoutError as e:
            raise AdviceError("timed out") from e
        except openai.RateLimitError as e:
            raise AdviceError("rate limited or out of credit") from e
        except openai.APIStatusError as e:
            raise AdviceError(f"API error {e.status_code}") from e
        except openai.APIConnectionError as e:
            raise AdviceError("network error") from e
        if response.status != "completed":
            reason = getattr(response.incomplete_details, "reason", None) or response.status
            raise AdviceError(f"incomplete: {reason}")
        try:
            answer = json.loads(response.output_text)
        except ValueError as e:
            raise AdviceError("answer was not JSON") from e
        u = response.usage
        details = getattr(u, "output_tokens_details", None)
        usage = {
            "input_tokens": int(u.input_tokens),
            "output_tokens": int(u.output_tokens),
            "reasoning_tokens": int(getattr(details, "reasoning_tokens", 0) or 0),
        }
        return answer, usage


def interpreter_from_env() -> Interpreter | None:
    """The interpreter the environment asks for, or None (advice then stays deterministic)."""
    provider = os.environ.get("AQUATRACK_ADVICE_PROVIDER", "").strip().lower()
    if provider in ("", "none", "off"):
        return None
    if provider != "openai":
        log.warning("unknown AQUATRACK_ADVICE_PROVIDER; advice stays deterministic")
        return None
    try:
        return OpenAIInterpreter()
    except (AdviceError, ImportError) as e:
        log.warning("advice model not available (%s); advice stays deterministic", e)
        return None


# ---------- the drills the model may choose from, and general practice ----------


def drill_list() -> list[dict]:
    return [
        {"drill_id": a.id, "name": a.name, "category": a.category, "purpose": a.purpose}
        for a in library.active()
        if a.category not in ("warm_up", "cool_down")
    ]


def general_practice(goals: list[str], level: str | None) -> list[AdvicePractice]:
    """Up to three library activities for the swimmer's goals (or general ones). Chosen
    without looking at the video: it does not mean a problem was found."""
    chosen, reason = [], ""
    pool = [a for a in library.active() if a.category not in ("warm_up", "cool_down")]
    pool = [a for a in pool if library.eligible(a, level, []) is None]
    for goal in goals:
        for a in pool:
            if goal in a.goals and a not in chosen:
                chosen.append(a)
    reason = "Chosen for the goals you set." if chosen else "General freestyle practice."
    for a in pool:  # fill up with general technique practice
        if len(chosen) >= 3:
            break
        if a not in chosen and a.id.startswith("tech."):
            chosen.append(a)
    return [
        AdvicePractice(
            activity_id=a.id,
            name=a.name,
            purpose=a.purpose,
            instructions=list(a.instructions),
            reason=reason + " It is not based on a problem found in this video.",
        )
        for a in chosen[:3]
    ]


# ---------- checks ----------


def _numbers(obj) -> set[float]:
    out: set[float] = set()
    for token in NUMBER.findall(json.dumps(obj)):
        v = float(token)
        for digits in (0, 1, 2, 3):
            out |= {round(v, digits), abs(round(v, digits))}
    return out


def _ungrounded(texts: list[str], allowed: set[float]) -> list[str]:
    """Numbers in the texts that are not a number of the profile. A number counts as found
    only at its own precision: "1.4" needs a measurement that rounds to 1.4, and "1.44" one
    that rounds to 1.44. Matching on the whole part alone would let any figure through."""
    bad = []
    for text in texts:
        for token in NUMBER.findall(text):
            v = float(token)
            if v not in allowed and abs(v) not in allowed:
                bad.append(token)
    return bad


def _ref_problem(ref: str, profile: dict, metrics: dict[str, str]) -> str | None:
    key = ref.strip()
    if key in metrics:
        return f"cites {key}, which was not measured" if metrics[key] == "unavailable" else None
    parts = key.replace("[", ".").replace("]", "").split(".")
    if parts[0] == "metrics" and len(parts) > 1 and parts[1] in metrics:
        return _ref_problem(parts[1], profile, metrics)
    if parts[0] not in PROFILE_ROOTS:
        return f"cites {key}, which is not in the data"
    node = profile
    for part in parts[:3]:  # the section and field must exist; deeper indexes are not followed
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, dict):
            return f"cites {key}, which is not in the data"
        else:
            break
    return None


class Checker:
    """Checks one answer against the profile it was made from."""

    def __init__(self, profile: dict):
        self.profile = profile
        self.allowed = _numbers(profile)
        self.metrics = {m["key"]: m["status"] for m in profile["metrics"]}
        self.duration = float(profile["clip"]["duration_s"] or 0)
        cycles = profile["stroke_cycles"]["cycles"]
        self.trusted_cycles = sum(1 for c in cycles if c.get("trusted"))
        self.tracking = profile["motion"]["tracking_of_followed_side"]
        self.drills = {d["drill_id"]: d for d in drill_list()}
        motion = profile["motion"]
        self.followed_trusted = sum(1 for c in motion["cycles"] if c.get("trusted"))
        self.series = motion["cycle_to_cycle"]
        self.resolution = float(motion["uncertainty"]["timing_resolution_s"])

    def exploratory(self, item: dict) -> bool:
        """Does the suggestion rest on raw leg positions instead of verified measurements?
        Decided from what it cites and what it is about, not from how it is worded."""
        listed = self.profile["motion"].get("exploratory", {})
        names = set(listed.get("features", [])) | set(listed.get("sample_fields", []))
        cited = {part for ref in item["evidence_refs"] for part in ref.replace("[", ".").split(".")}
        return item["category"] == "legs" or bool(names & cited)

    def tentative(self, item: dict) -> list[str]:
        """Why a suggestion that passed the checks is still only a first indication. These
        are facts about the sample, decided here; the model's confidence plays no part."""
        reasons = []
        if self.exploratory(item):
            reasons.append(
                "Based on leg positions that AquaTrack does not yet verify as a measurement "
                "(the kick has not been checked against video). Treat it as something to look "
                "at in your video, not as a finding."
            )
        n = min(item["cycles_supporting"], self.followed_trusted or item["cycles_supporting"])
        if self.followed_trusted < MIN_CYCLES_FOR_FIRM or n < MIN_CYCLES_FOR_FIRM:
            seen = self.followed_trusted if self.followed_trusted < MIN_CYCLES_FOR_FIRM else n
            reasons.append(
                f"Based on only {seen} stroke cycle{'s' if seen != 1 else ''}: a first "
                "indication to check on a longer clip, not an established pattern."
            )
        timing = [
            ref.split(".")[-1]
            for ref in item["evidence_refs"]
            if ref.split(".")[-1] in TIMING_FEATURES and ref.split(".")[-1] != "cycle_duration_s"
        ]
        spreads = [
            self.series[k]["max"] - self.series[k]["min"]
            for k in timing
            if "max" in self.series.get(k, {})
        ]
        if spreads and max(spreads) < MIN_FRAMES_FOR_TIMING * self.resolution:
            reasons.append(
                "The timing differences it rests on are within a few video frames, close to "
                "the limit of what the video can time."
            )
        return reasons

    def common(self, texts: list[str], refs: list[str], times: list[float]) -> list[str]:
        reasons = []
        bad = _ungrounded(texts, self.allowed)
        if bad:
            reasons.append(f"states numbers that are not in the measurements: {', '.join(bad[:5])}")
        for ref in refs:
            problem = _ref_problem(ref, self.profile, self.metrics)
            if problem:
                reasons.append(problem)
        if any(not (0 <= t <= self.duration + 0.05) for t in times):
            reasons.append("refers to a time outside the clip")
        text = " ".join(texts)
        if UNSAFE.search(text):
            reasons.append("breath-holding or hypoxic work")
        if PROMISE.search(text):
            reasons.append("promises a result")
        return reasons

    def statement(self, item: dict) -> list[str]:
        reasons = self.common([item["statement"]], item["evidence_refs"], item["times_s"])
        if not item["evidence_refs"] and not NUMBER.search(item["statement"]):
            reasons.append("gives no measurement or reference to support it")
        return reasons

    def suggestion(self, item: dict) -> list[str]:
        texts = [
            item[k]
            for k in (
                "title",
                "noticed",
                "why_it_may_matter",
                "try_this",
                "drill_note",
                "check_next_time",
            )
        ]
        reasons = self.common(texts, item["evidence_refs"], item["times_s"])
        if not item["evidence_refs"]:
            reasons.append("names no measurement it is based on")
        n = item["cycles_supporting"]
        if n < MIN_CYCLES_FOR_PATTERN:
            reasons.append("seen in fewer than two stroke cycles: not a repeated pattern")
        elif n > max(self.trusted_cycles, len(self.profile["motion"]["cycles"])):
            reasons.append("claims more stroke cycles than were measured")
        for joint in CATEGORY_JOINTS.get(item["category"], ()):
            share = self.tracking.get(joint, {}).get("usable_share", 1.0)
            if share < MIN_USABLE_SHARE:
                reasons.append(
                    f"is about the {joint}, which was usable in only {share:.0%} of the frames"
                )
        if IDEAL.search(" ".join(texts)):
            reasons.append("prescribes an ideal angle or position")
        return reasons


def check(answer: dict, profile: dict) -> dict:
    """Split a model answer into what passed and what was dropped, piece by piece."""
    checker = Checker(profile)
    kept = {"observations": [], "consistent": [], "suggestions": [], "rejected": []}
    for kind, target in (("observations", "observation"), ("consistent", "consistent")):
        for item in answer.get(kind, []):
            reasons = checker.statement(item)
            if reasons:
                kept["rejected"].append(
                    AdviceRejected(kind=target, title=item["statement"][:120], reasons=reasons)
                )
            else:
                kept[kind].append(AdviceObservation(**item))
    for item in answer.get("suggestions", []):
        reasons = checker.suggestion(item)
        if not reasons and len(kept["suggestions"]) >= MAX_SUGGESTIONS:
            reasons = ["more than three suggestions: only the first three are kept"]
        if reasons:
            kept["rejected"].append(
                AdviceRejected(kind="suggestion", title=item["title"][:120], reasons=reasons)
            )
            continue
        drill = checker.drills.get(item["drill_id"])
        kept["suggestions"].append(
            AdviceSuggestion(
                id=f"s{len(kept['suggestions']) + 1}",
                title=item["title"],
                category=item["category"],
                noticed=item["noticed"],
                why_it_may_matter=item["why_it_may_matter"],
                try_this=item["try_this"],
                drill_id=drill["drill_id"] if drill else "",  # an unknown drill is dropped
                drill_name=drill["name"] if drill else "",
                drill_how=item["drill_note"],
                check_next_time=item["check_next_time"],
                confidence=item["confidence"],
                cycles_supporting=item["cycles_supporting"],
                evidence_refs=item["evidence_refs"],
                times_s=item["times_s"],
                tentative=bool(checker.tentative(item)),
                tentative_reasons=checker.tentative(item),
                evidence_basis="exploratory" if checker.exploratory(item) else "measured",
            )
        )
    # Measured evidence first: an exploratory suggestion never leads the list.
    kept["suggestions"].sort(key=lambda s: s.evidence_basis == "exploratory")
    for n, s in enumerate(kept["suggestions"], 1):
        s.id = f"s{n}"
    kept["trusted_cycles"] = checker.followed_trusted
    return kept


# ---------- building the document ----------

LIMITATIONS = [
    "The suggestions are an AI model's interpretation of the measurements. They are ideas "
    "to try, not confirmed technique faults, and no coach has reviewed this swim.",
    "The model was given measurements only, not the video.",
    "One underwater side camera: movement toward or away from the camera, the far arm and "
    "the above-water recovery are not seen.",
    "Checked against synthetic swimmers and a few clips only; not validated for accuracy on "
    "real swimmers.",
]


def advice_id(analysis_id: str, profile_sha256: str, model: str) -> str:
    """The same analysis, measurements, model, prompt and version always give the same id,
    so opening a result or analysing again never pays for the same interpretation twice."""
    import hashlib

    from aquatrack.contracts import ADVICE_VERSION

    key = json.dumps([analysis_id, profile_sha256, model, PROMPT_VERSION, ADVICE_VERSION])
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def _base(result: AnalysisResult, analysis_id: str, profile: dict, goals, level) -> dict:
    return {
        "video_id": result.video_id,
        "analysis_id": analysis_id,
        "profile_version": profile["profile_version"],
        "profile_sha256": motion_profile.digest(profile),
        "analysis_schema_version": result.schema_version,
        "engine_version": result.engine_version or __version__,
        "library_version": library.LIBRARY_VERSION,
        "general_practice": general_practice(goals, level),
    }


def deterministic(result, analysis_id, profile, goals, level, reason: str) -> Advice:
    return Advice(
        **_base(result, analysis_id, profile, goals, level),
        source="deterministic",
        fallback_reason=reason,
    )


def build_advice(
    result: AnalysisResult,
    analysis_id: str,
    profile: dict,
    interpreter: Interpreter | None,
    goals: list[str] | None = None,
    level: str | None = None,
) -> Advice:
    """The advice for one analysis. Never raises for a model problem: it falls back."""
    goals = goals or []
    if interpreter is None:
        return deterministic(result, analysis_id, profile, goals, level, "AI advice is not enabled")
    if not any(c.get("trusted") for c in profile["stroke_cycles"]["cycles"]):
        # Nothing was followed well enough to interpret: no call is made for it.
        return deterministic(
            result, analysis_id, profile, goals, level, "no stroke cycle could be measured"
        )
    payload = {
        "swimmer_goals": goals,
        "swimmer_level": level or "not given",
        "drills_you_may_choose": drill_list(),
        "data": profile,
    }
    try:
        answer, usage = interpreter.interpret(payload)
        kept = check(answer, profile)
    except AdviceError as e:
        log.warning("advice model failed: %s", e)
        return deterministic(result, analysis_id, profile, goals, level, f"the AI call failed: {e}")
    except (KeyError, TypeError, ValueError) as e:  # an answer that does not fit the schema
        log.warning("advice answer unusable: %s", type(e).__name__)
        return deterministic(
            result, analysis_id, profile, goals, level, "the AI answer could not be read"
        )
    if not (kept["observations"] or kept["consistent"] or kept["suggestions"]):
        fallback = deterministic(
            result, analysis_id, profile, goals, level, "nothing in the AI answer passed the checks"
        )
        fallback.rejected = kept["rejected"]
        return fallback
    quality = [
        f"{q['problem']} ({q['affects']})" if q.get("affects") else q["problem"]
        for q in answer.get("data_quality", [])
        if not _ungrounded([q["problem"], q.get("affects", "")], _numbers(profile))
    ]
    summary = answer.get("summary", "")
    if _ungrounded([summary], _numbers(profile)) or UNSAFE.search(summary):
        summary = ""
    return Advice(
        **_base(result, analysis_id, profile, goals, level),
        source="ai",
        model=interpreter.model,
        reasoning_effort=interpreter.reasoning,
        prompt_version=PROMPT_VERSION,
        usage=usage,
        trusted_cycles=kept["trusted_cycles"],
        summary=summary,
        data_quality=quality,
        observations=kept["observations"],
        consistent=kept["consistent"],
        suggestions=kept["suggestions"],
        rejected=kept["rejected"],
        limitations=LIMITATIONS,
    )
