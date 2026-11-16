# OpenAI adapter: review and live-test procedure

**No real API call has been made.** Do not run section 3 without the owner's approval for
that run.

## 1. Review of the adapter (`src/aquatrack/analysis/explain.py`)

| Point | State |
| --- | --- |
| SDK | official `openai` Python SDK 3.51.0 (locked in `uv.lock`); the request is built by the real SDK in tests |
| API | Responses API: `client.responses.create(model, instructions, input, text.format, max_output_tokens, reasoning, store)` |
| Structured output | `text.format = {type: json_schema, strict: true}`; schemas list every property as required and forbid extras (tested) |
| Timeout and retry | 20 s per request (`AQUATRACK_LLM_TIMEOUT_S`), one SDK retry; any failure falls back to the app's own text |
| Output bound | `max_output_tokens` 4,000 including reasoning tokens |
| Cost controls | off by default; one call per analysed video and per saved plan; **daily ceiling per process** (`AQUATRACK_LLM_MAX_CALLS_PER_DAY`, default 200; added in Phase 7); request rate limits on the routes that can trigger a call; cheapest listed model by default |
| Privacy | no identifiers, video, pose data, names, emails, notes or typed-in activities are sent (tested); `store=False` |
| Prompt injection | nothing the swimmer typed is in the payload; the instructions say the input is data; the answer is validated and discarded on any violation |
| Validation | feedback: `explain.validate`; plans: `training.explain.validate_plan`. One violation rejects the whole answer |
| Fallback | no model, a failure or a rejection all show the deterministic text; nothing depends on the model |
| Credentials | read from the environment by the SDK; never logged, stored or returned (tested) |
| Refusals, cut-offs, bad JSON | each becomes one plain error and a fallback (tested with mocked responses) |

Not verified, because it needs a real call: that the account can use `gpt-6-luna`; that the
model accepts `reasoning.effort = low` with a strict schema; real latency, token use and
cost; how often real answers pass validation. `store=False` does not switch off OpenAI's
abuse-monitoring logs (up to 30 days unless Zero Data Retention is approved).

## 2. Model

`gpt-6-luna`: listed by OpenAI at $0.10 per million input tokens and $0.50 per million output
tokens (pricing page read 2026-11-16), with structured outputs and the Responses API. Change
it with `AQUATRACK_LLM_MODEL`.

## 3. Live-test procedure (needs approval)

| Item | Value |
| --- | --- |
| Script | `scripts/llm_live_check.py --confirm-billable-calls` (refuses to run without the flag) |
| Model | `gpt-6-luna` |
| Calls | 3 at most (the script sets the daily ceiling to 3): a goal-based plan, an analysis-based plan, one feedback |
| Input | labelled synthetic fixtures from the unit tests; nothing about a real person |
| Expected tokens per call | about 1,500 to 3,000 input, up to 4,000 output (estimate) |
| Estimated maximum cost | 3 x (3,000 x $0.10 + 4,000 x $0.50) / 1,000,000 = about $0.007; budget $0.05 to allow for retries (estimate from list prices) |
| Environment | `AQUATRACK_LLM_PROVIDER=openai`, `OPENAI_API_KEY` set in your own shell or untracked `.env`; optional `AQUATRACK_LLM_MODEL` |
| Install | `uv sync --extra llm` |

Steps:

1. In your own terminal (never in a chat): `export OPENAI_API_KEY=...` and
   `export AQUATRACK_LLM_PROVIDER=openai`.
2. `uv run --extra llm python scripts/llm_live_check.py --confirm-billable-calls`
3. Read the three lines it prints: `llm` means the answer passed validation; `template` with
   a note means it was rejected or the call failed, and the note says why.
4. Check the usage page of the OpenAI account for the actual cost.

What to do with the outcome: a rejection is not a failure of the test; it is the validator
working. A model or parameter error (for example an unknown model or an unsupported
`reasoning` value) means changing `AQUATRACK_LLM_MODEL` or `AQUATRACK_LLM_REASONING`, not the
code.

## 4. Switching it off at once

Unset `AQUATRACK_LLM_PROVIDER` (or set it to `none`) and restart the API. Nothing else is
needed: with it unset no client is created and no request can be made. Revoking the key in
the OpenAI dashboard stops everything regardless of configuration.
