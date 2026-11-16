"""A small LIVE check of the OpenAI rewording adapter. It makes real, billed API calls.

DO NOT RUN without the owner's explicit approval for that run. It refuses to start unless
`--confirm-billable-calls` is given, and it never prints or stores the API key.

    AQUATRACK_LLM_PROVIDER=openai OPENAI_API_KEY=... \\
        uv run --extra llm python scripts/llm_live_check.py --confirm-billable-calls

What it does (see docs/OPENAI_LIVE_TEST.md for the full procedure and cost estimate):
  1. one call rewording a SYNTHETIC goal-based weekly plan
  2. one call rewording a SYNTHETIC analysis-based weekly plan
  3. one call rewording SYNTHETIC feedback
At most 3 calls, each bounded by AQUATRACK_LLM_MAX_OUTPUT_TOKENS. Nothing about a real
swimmer is sent: every input is a labelled synthetic fixture from the unit tests. For each
call it reports whether the answer passed validation or why it was rejected, and the token
usage the API reported.
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-billable-calls", action="store_true")
    args = parser.parse_args()
    if not args.confirm_billable_calls:
        print("Refusing to run: this makes real billed calls. See docs/OPENAI_LIVE_TEST.md.")
        return 2
    os.environ["AQUATRACK_LLM_MAX_CALLS_PER_DAY"] = "3"  # a hard stop for this run
    from aquatrack.analysis import explain
    from aquatrack.training import planner
    from aquatrack.training.explain import explain_plan

    model = explain.explainer_from_env()
    if model is None:
        print("Rewording is off: set AQUATRACK_LLM_PROVIDER=openai and OPENAI_API_KEY.")
        return 2
    print(f"model: {model.model}; at most 3 calls")
    from test_feedback import feedback as synthetic_feedback
    from test_training import SUPPORTED, profile

    swimmer = planner.swimmer_from_profile(profile())
    for label, ctx in (
        ("goal-based plan", planner.AnalysisContext()),
        ("analysis-based plan", SUPPORTED),
    ):
        plan = explain_plan(planner.build_week(swimmer, ctx, date(2026, 11, 16)), model)
        print(f"{label}: {plan.explanation.source} {plan.explanation.note}")
        if plan.explained:
            print("  ", plan.explained)
    fb = explain.explain_feedback(synthetic_feedback(), model)
    print(f"feedback: {fb.explanation.source} {fb.explanation.note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
