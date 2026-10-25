"""Does a generated result answer the question as the reference SQL does?

Execution accuracy, made tolerant to what does not change the answer and strict on what
does. Tolerated: extra columns, other column names, column order, a percentage where the
reference has a ratio (43.2 for 0.432), rounding (a cent on amounts, 0.0005 on ratios),
a timestamp at midnight where the reference has a date. Not tolerated: a missing column
of the reference, a different number of rows (except in ``contains`` mode), a wrong value.

Modes:
- ``rows``: same rows, in any order (``ordered=True``: in the same order).
- ``first``: the reference has one row; each of its values must be in the generated
  first row. For "which X ..." questions, where the model may list more than one X.
- ``contains``: every reference row is among the generated rows.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from itertools import product
from typing import Literal

MatchMode = Literal["rows", "first", "contains"]
Row = Sequence[object]
MAX_MAPPINGS = 256


@dataclass(frozen=True)
class Match:
    ok: bool
    reason: str


def _number(value: object) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, Decimal)):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    return None


def _close(expected: Decimal, actual: Decimal, tolerance: Decimal) -> bool:
    # The relative part only absorbs float noise on very large totals.
    return abs(expected - actual) <= max(tolerance, abs(expected) * Decimal("1e-9"))


def values_equal(expected: object, actual: object) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is type(actual) and expected == actual
    expected_number, actual_number = _number(expected), _number(actual)
    if expected_number is not None and actual_number is not None:
        if abs(expected_number) < 1:
            # A ratio: rounded to 3-4 decimals, or written as a percentage (43.2 for 0.432).
            return _close(expected_number, actual_number, Decimal("0.0005")) or _close(
                expected_number * 100, actual_number, Decimal("0.05")
            )
        # Amounts and counts: a cent absorbs rounding to 2 decimals.
        return _close(expected_number, actual_number, Decimal("0.01"))
    if isinstance(expected, (date, datetime)) and isinstance(actual, (date, datetime)):
        return _as_date(expected) == _as_date(actual)
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip() == actual.strip()
    return False


def _as_date(value: date | datetime) -> date | datetime:
    if isinstance(value, datetime):
        return value.date() if value.time() == datetime.min.time() else value
    return value


def _column(rows: Sequence[Row], index: int) -> list[object]:
    return [row[index] for row in rows]


def _same_values(expected: list[object], actual: list[object]) -> bool:
    """Equal multisets of values, with the tolerances of values_equal."""
    remaining = list(actual)
    for value in expected:
        for i, candidate in enumerate(remaining):
            if values_equal(value, candidate):
                del remaining[i]
                break
        else:
            return False
    return not remaining


def _rows_match(
    expected: Sequence[Row],
    actual: Sequence[Row],
    mapping: tuple[int, ...],
    *,
    ordered: bool,
    subset: bool,
) -> bool:
    projected = [tuple(row[k] for k in mapping) for row in actual]
    if ordered:
        return all(
            all(values_equal(e, a) for e, a in zip(exp, act, strict=True))
            for exp, act in zip(expected, projected, strict=False)
        ) and len(projected) >= len(expected)
    remaining = list(projected)
    for exp in expected:
        for i, act in enumerate(remaining):
            if all(values_equal(e, a) for e, a in zip(exp, act, strict=True)):
                del remaining[i]
                break
        else:
            return False
    return subset or not remaining


def compare(
    expected: Sequence[Row],
    actual: Sequence[Row],
    *,
    mode: MatchMode = "rows",
    ordered: bool = False,
) -> Match:
    if not expected:
        return Match(not actual, "both empty" if not actual else "the reference is empty")
    if not actual:
        return Match(False, "no rows returned")
    width = len(expected[0])

    if mode == "first":
        if len(expected) != 1:
            raise ValueError("mode 'first' needs a one-row reference")
        cells = list(actual[0])
        for value in expected[0]:
            for i, cell in enumerate(cells):
                if values_equal(value, cell):
                    del cells[i]
                    break
            else:
                return Match(False, f"{value!r} is not in the first row")
        return Match(True, "the first row holds the reference values")

    if mode == "rows" and len(actual) != len(expected):
        return Match(False, f"{len(actual)} rows instead of {len(expected)}")
    if len(actual[0]) < width:
        return Match(False, f"{len(actual[0])} columns, the reference has {width}")

    # Candidate generated columns for each reference column.
    candidates: list[list[int]] = []
    for j in range(width):
        reference = _column(expected, j)
        found = []
        for k in range(len(actual[0])):
            column = _column(actual, k)
            if mode == "rows":
                if _same_values(reference, column):
                    found.append(k)
            elif all(any(values_equal(v, c) for c in column) for v in reference):
                found.append(k)
        if not found:
            return Match(False, f"no column holds the values of reference column {j + 1}")
        candidates.append(found)

    for count, mapping in enumerate(product(*candidates)):
        if count >= MAX_MAPPINGS:
            break
        if len(set(mapping)) != len(mapping):
            continue
        if _rows_match(expected, actual, mapping, ordered=ordered, subset=mode == "contains"):
            return Match(True, "rows match")
    return Match(False, "columns match one by one but not row by row")
