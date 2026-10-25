"""Figures computed by code from a query result, before any text is written.

The model explains; it does not compute. Totals, extremes, averages, shares and changes
between the first and the last row are computed here, exactly, and handed to the model
as named facts. Every number the explanation cites must be one of the result values or
one of these facts (eaa.analysis.numbers).
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from eaa.privacy.payload import ProviderPayload

MAX_SHARE_ROWS = 20


@dataclass(frozen=True)
class Fact:
    name: str
    value: Decimal


def _numeric_columns(payload: ProviderPayload) -> list[int]:
    indexes = []
    for i in range(len(payload.columns)):
        values = [row[i] for row in payload.rows if row[i] is not None]
        if values and all(
            isinstance(v, (int, float, Decimal)) and not isinstance(v, bool) for v in values
        ):
            indexes.append(i)
    return indexes


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def compute_facts(payload: ProviderPayload) -> list[Fact]:
    facts = [Fact("row_count", Decimal(payload.total_rows))]
    if len(payload.rows) < 2:
        return facts
    for i in _numeric_columns(payload):
        name = payload.columns[i]
        values = [_decimal(row[i]) for row in payload.rows if row[i] is not None]
        total = sum(values, Decimal(0))
        facts += [
            Fact(f"{name}.total", total),
            Fact(f"{name}.average", total / len(values)),
            Fact(f"{name}.max", max(values)),
            Fact(f"{name}.min", min(values)),
        ]
        first, last = values[0], values[-1]
        facts.append(Fact(f"{name}.last_minus_first", last - first))
        if first != 0:
            facts.append(Fact(f"{name}.last_vs_first_change", last / first - 1))
        if total > 0 and all(v >= 0 for v in values) and len(values) <= MAX_SHARE_ROWS:
            facts += [
                Fact(f"{name}.share_of_total[row {n}]", value / total)
                for n, value in enumerate(values, start=1)
            ]
    return facts
