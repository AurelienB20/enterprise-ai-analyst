"""Validate a query and run it as eaa_reader, the way generated SQL will run.

uv run python -m eaa.execution "SELECT region, COUNT(*) FROM customers GROUP BY 1"
"""

import argparse
import sys

from eaa.config import get_settings
from eaa.execution.executor import ExecutionError, ExecutionLimits, ReadOnlyExecutor
from eaa.semantic.model import load
from eaa.sql_security.validator import SQLRejectedError, SQLValidator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eaa.execution", description=__doc__)
    parser.add_argument("sql")
    args = parser.parse_args(argv)

    settings = get_settings()
    try:
        query = SQLValidator(load()).validate(args.sql)
    except SQLRejectedError as error:
        print(f"Rejected ({error.reason}): {error.message}", file=sys.stderr)
        return 2
    print(f"Runs: {query.sql}\nViews: {', '.join(sorted(query.views))}\n")
    executor = ReadOnlyExecutor(
        settings.require_reader_database_url(),
        ExecutionLimits(timeout_ms=settings.query_timeout_ms, max_rows=settings.query_max_rows),
    )
    try:
        result = executor.execute(query)
    except ExecutionError as error:
        print(f"Failed ({error.kind}): {error.message}", file=sys.stderr)
        return 1
    print(" | ".join(column.name for column in result.columns))
    for row in result.rows[:50]:
        print(" | ".join(str(value) for value in row))
    shown = min(len(result.rows), 50)
    more = " (truncated by the row limit)" if result.truncated else ""
    print(f"\n{shown} of {len(result.rows)} rows shown{more}, {result.duration_ms} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
