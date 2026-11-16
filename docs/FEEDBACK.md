# Feedback, checkpoints and the language-model guard (feedback 1.0)

Code: `src/aquatrack/analysis/feedback.py`, `src/aquatrack/analysis/explain.py`.
Flow: metrics (Phase 2) -> interpretation (Phase 3) -> profile and goals -> evidence library ->
feedback -> optional rewording -> screen.

## Five categories, never mixed

| Category | Comes from | May say | May not say |
| --- | --- | --- | --- |
| observation | an interpretation observation | what was measured, with timestamps | that anything is a problem |
| focus | an interpretation issue candidate | what was seen, why it may matter (with its source and limits) | that it is a confirmed fault |
| priority | an interpretation priority (at most three) | the same, plus why it is ranked and what to watch | anything about expected results |
| education | a goal on the swimmer's profile | what verified research says in general, and what AquaTrack can and cannot look at for that goal | anything about this swimmer's video; it has no rank and no measurements |
| insufficient | an interpretation "undetermined" entry | the limit and what footage or information would help | that the limit reflects on the swimmer |

Feedback never creates a finding: observations, focus items and priorities map one-to-one to the
interpretation. Goals add education and affect priority ranking (through the interpretation) only.
Choosing "breathing" produces a general note that breathing cannot be measured, nothing else.

## Goals

Optional on the profile: `goals` (any of stroke_consistency, body_alignment, arm_technique,
speed, endurance, breathing, overall_freestyle), `primary_goal` (one of the chosen), `target`
(event, pool, seconds) and `weak_note` (free text, at most 200 characters). Validated by
`firebase/firestore.rules`. `weak_note` and `target` are stored and shown back to the swimmer;
they are not analysed and are never sent to a language model. Profiles without these fields work
as before.

## Checkpoints

What to film and look for next time; not a drill, plan or promise.

| Id | When | Content |
| --- | --- | --- |
| cp.recurs.<finding> | a focus or priority exists | film the same task again; the same pattern in a second comparable swim is what makes it a priority |
| cp.side_view | camera view changed, camera side unclear, or nothing measured | side-on, steady, whole body in view |
| cp.longer_clip | fewer than 6 cycles of one arm | at least 6 cycles, with the seconds that needs at this tempo |
| cp.repeat_same_conditions | baseline with measured observations | same task, same filming; what size of difference counts (from the interpretation's resolution table) |

At most four.

Since Phase 5 each checkpoint also stores `reason`, `baseline` (the values measured in its
video, with their reliability), `source_video_id`, `source_analysis_id` and `created_at`. When
a later video is interpreted, the previous analysed video's checkpoints are followed up and the
result is stored in that video's feedback as `followups` (states and wording:
`docs/HISTORY_AND_DELETION.md`, section 4). Follow-ups are part of the feedback id, and earlier
feedback documents are never modified.

## Language-model rewording (optional, off by default)

- Provider: OpenAI, through the official Python SDK and the Responses API with a strict JSON
  schema (`text.format`), `store=False`, a timeout (20 s), one retry and a bounded output
  (4,000 tokens, which includes the model's own reasoning). The earlier Anthropic adapter and
  dependency were removed in Phase 6; the validation and fallback below are unchanged.
- Switched on only when all three hold: `AQUATRACK_LLM_PROVIDER=openai`, the `llm` extra
  installed (`uv sync --extra llm`), and `OPENAI_API_KEY` in the backend's environment. A key
  alone switches nothing on. The key is read by the SDK from the environment: it is never in
  git, never sent to the web app, never logged. Each feedback and each saved plan then makes
  one billed call. **No real call has been made in development or tests.**
- Model: `gpt-6-luna` by default (`AQUATRACK_LLM_MODEL` to change it). OpenAI's model page
  (read 2026-11-16) lists it as the most efficient option for focused, high-volume tasks, with
  structured outputs and the Responses API, at $0.10 per million input tokens and $0.50 per
  million output tokens. Rewording a few short, already written items needs nothing larger.
  At the 4,000-token output bound one call costs at most about $0.003. Other settings:
  `AQUATRACK_LLM_TIMEOUT_S`, `AQUATRACK_LLM_MAX_OUTPUT_TOKENS`, `AQUATRACK_LLM_REASONING`
  (default `low`; empty to omit).
- Tests drive the real SDK against a fake HTTP transport, so the request body is the one the
  SDK would send; every answer is mocked, and any attempt to open a real connection fails
  the test.
- Training plans are reworded the same way with their own checks: `docs/TRAINING.md`, section 7.
- Sent: item ids, categories, the deterministic text, limitations, attached claim ids and
  statements, swim level and goal keys. Not sent: video, pose data, names, email, account or
  video ids, the swimmer's own note.
- The answer is validated against the feedback it was asked to reword. One failure rejects the
  whole answer:
  - unknown or repeated item id (the model may not add or duplicate findings);
  - any number that is not in that item's own text or measurements;
  - a citation id not attached to that item, or a study named that is not attached to it;
  - never-allowed claims (guarantees, speed promises, injury or medical language, target angles,
    breath-holding, "a coach reviewed");
  - an observation, education or insufficient item worded as a judgement;
  - an education item worded as a personal finding;
  - a focus or priority worded as a confirmed fault;
  - empty text or more than 900 characters.
- The deterministic text (`body`) is always stored. Reworded text goes in `explained` and is used
  only when the whole answer passed. An unreachable API, a refusal or bad JSON leaves the
  feedback exactly as it was. The screen always shows numbers and references from the
  structured fields, not from the model's text.
- Known limits of the guard: it is pattern-based. It cannot catch every unsupported sentence
  that contains no number, citation or listed phrase. It has only been exercised with mocks.

## Storage

`videos/{id}/feedback/{feedbackId}`, owner read, backend write. The id is a hash of the
interpretation's content, the feedback and evidence versions, the goals and the explanation
source: the same inputs reuse the stored document, different inputs add a new one, nothing is
overwritten. Each document records `feedback_version`, `evidence_version`, `rules_version`,
`interpretation_id`, `goals_used` and the explanation source. `POST /videos/{id}/interpret`
regenerates interpretation and feedback from the stored analysis without pose inference.

## Not validated

Whether this feedback helps anyone swim better is unknown. The tests use a synthetic swimmer,
labelled synthetic history and a mocked model.
