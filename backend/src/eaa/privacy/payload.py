"""What may leave the backend for the LLM provider, built from a query result.

- ``pii`` columns are dropped (they cannot come from the views; this is the last guard).
- ``confidential`` values are pseudonymised: each distinct value becomes a stable token
  such as ``CUSTOMER_001``. The mapping stays in the backend, in memory, for one
  analysis: it lets the answer show real names to the user, and it is never sent, logged
  or stored. Pseudonymised data is NOT anonymous: whoever holds the mapping, or enough
  context, can re-identify (docs/privacy.md).
- At most ``max_rows`` rows: the provider gets the aggregates that answer the question,
  not a table to browse.

Milestone 0.7 sends this payload to the model to explain the result.
"""

from dataclasses import dataclass, field
from typing import Any

from eaa.execution.executor import QueryResult
from eaa.privacy.lineage import ColumnLineage

# Token prefixes by source column; anything else confidential becomes ENTITY_n.
PREFIXES = {"customers.customer_name": "CUSTOMER"}


@dataclass
class Pseudonymizer:
    """One per analysis: the same value always gets the same token within it."""

    tokens: dict[tuple[str, Any], str] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)

    def token(self, prefix: str, value: Any) -> str:
        key = (prefix, value)
        if key not in self.tokens:
            self.counters[prefix] = self.counters.get(prefix, 0) + 1
            self.tokens[key] = f"{prefix}_{self.counters[prefix]:03d}"
        return self.tokens[key]

    def reveal(self, text: str) -> str:
        """Put the real values back into a text written from the payload."""
        for (_, value), token in sorted(self.tokens.items(), key=lambda kv: -len(kv[1])):
            text = text.replace(token, str(value))
        return text


@dataclass(frozen=True)
class ProviderPayload:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    total_rows: int
    pseudonymised_columns: tuple[str, ...]
    dropped_columns: tuple[str, ...]


def build_payload(
    result: QueryResult,
    columns: tuple[ColumnLineage, ...],
    pseudonymizer: Pseudonymizer,
    *,
    max_rows: int = 50,
) -> ProviderPayload:
    # Lineage is matched by position: the result columns come in the order of the SELECT.
    # If the counts differ, no column is trusted.
    known = len(columns) == len(result.columns)
    keep: list[int] = []
    prefixes: dict[int, str] = {}
    dropped: list[str] = []
    for index, column in enumerate(result.columns):
        lineage = columns[index] if known else None
        # Without lineage, a column is assumed confidential, never harmless.
        classification = lineage.classification if lineage else "confidential"
        if classification == "pii":
            dropped.append(column.name)
            continue
        keep.append(index)
        if classification == "confidential":
            sources = lineage.sources if lineage else ()
            prefixes[index] = next((PREFIXES[s] for s in sources if s in PREFIXES), "ENTITY")
    rows = tuple(
        tuple(
            pseudonymizer.token(prefixes[i], row[i])
            if i in prefixes and row[i] is not None
            else row[i]
            for i in keep
        )
        for row in result.rows[:max_rows]
    )
    return ProviderPayload(
        columns=tuple(result.columns[i].name for i in keep),
        rows=rows,
        total_rows=len(result.rows),
        pseudonymised_columns=tuple(result.columns[i].name for i in prefixes),
        dropped_columns=tuple(dropped),
    )
