"""Ask one question through the whole pipeline. Calls the LLM: it costs money.

uv run python -m eaa.orchestrator "Quel est le chiffre d'affaires du mois dernier ?"
"""

import argparse
import sys

from eaa.config import get_settings
from eaa.services import build_services


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eaa.orchestrator", description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--no-record", action="store_true", help="skip the audit trail")
    args = parser.parse_args(argv)

    services = build_services(get_settings())
    analysis = services.pipeline.run(args.question)
    if not args.no_record:
        services.store.record(analysis, correlation_id="cli")

    print(f"Status: {analysis.status}  ({analysis.id})")
    for number, attempt in enumerate(analysis.attempts, start=1):
        note = f": {attempt.message}" if attempt.message else ""
        print(f"\nAttempt {number} {attempt.outcome}{note}\n  {attempt.sql}")
    if analysis.proposal is not None:
        print(f"\nExplanation: {analysis.proposal.explanation}")
        for assumption in analysis.proposal.assumptions:
            print(f"Assumption: {assumption}")
        for ambiguity in analysis.proposal.ambiguities:
            print(f"Ambiguity: {ambiguity}")
    if analysis.declined is not None:
        print(f"\nDeclined ({analysis.declined.reason}): {analysis.declined.message}")
    elif analysis.error_message:
        print(f"\nError ({analysis.error_kind}): {analysis.error_message}")
    if analysis.result is not None:
        print("\n" + " | ".join(column.name for column in analysis.result.columns))
        for row in analysis.result.rows[:20]:
            print(" | ".join(str(value) for value in row))
        if len(analysis.result.rows) > 20 or analysis.result.truncated:
            print("...")
    usage = analysis.usage
    print(
        f"\n{usage.calls} LLM call(s), {usage.input_tokens} input + {usage.cache_read_tokens} "
        f"cached + {usage.output_tokens} output tokens, ${analysis.cost_usd:.4f}, "
        f"{analysis.total_ms / 1000:.1f} s (generation {analysis.generation_ms / 1000:.1f} s, "
        f"SQL {analysis.execution_ms:.0f} ms)"
    )
    return 0 if analysis.status == "answered" else 1


if __name__ == "__main__":
    sys.exit(main())
