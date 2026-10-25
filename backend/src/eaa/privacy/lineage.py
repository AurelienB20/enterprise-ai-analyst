"""Which view columns each result column comes from, and so its classification.

A result column inherits the most sensitive classification among the view columns it is
computed from: ``UPPER(customer_name)`` is still confidential, ``SUM(net_revenue)`` is
internal. Found with SQLGlot's column lineage, through CTEs and subqueries. A column
computed from no view column (a constant, ``COUNT(*)``) is internal.

If the lineage cannot be computed, every column is treated as confidential: an unknown
column is never assumed harmless.
"""

import logging
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.lineage import lineage
from sqlglot.optimizer.qualify import qualify

from eaa.semantic.model import Classification, SemanticModel

logger = logging.getLogger(__name__)

RANK: dict[Classification, int] = {"public": 0, "internal": 1, "confidential": 2, "pii": 3}


@dataclass(frozen=True)
class ColumnLineage:
    name: str
    sources: tuple[str, ...]  # "view.column"
    classification: Classification


class LineageResolver:
    def __init__(self, model: SemanticModel) -> None:
        self._schema: dict[str, object] = {
            "analytics": {
                view.name: {column.name: column.type for column in view.columns}
                for view in model.views
            }
        }
        self._classification = {
            (view.name, column.name): column.classification
            for view in model.views
            for column in view.columns
        }

    def resolve(self, sql: str) -> tuple[ColumnLineage, ...]:
        try:
            tree = qualify(
                sqlglot.parse_one(sql, dialect="postgres"),
                schema=self._schema,
                db="analytics",
                dialect="postgres",
            )
            if not isinstance(tree, exp.Query):
                raise SqlglotError("not a query")
            return tuple(self._column(tree, select.alias_or_name) for select in tree.selects)
        except SqlglotError as error:
            logger.warning("Lineage unavailable, treating every column as confidential: %s", error)
            return ()

    def _column(self, tree: exp.Query, name: str) -> ColumnLineage:
        node = lineage(name, tree, schema=self._schema, dialect="postgres")
        sources: set[tuple[str, str]] = set()
        for leaf in node.walk():
            if leaf.downstream or not isinstance(leaf.source, exp.Table):
                continue
            column = leaf.name.split(".")[-1].strip('"')
            sources.add((leaf.source.name, column))
        classifications = [self._classification.get(s, "confidential") for s in sources]
        classification: Classification = max(
            classifications, key=lambda c: RANK[c], default="internal"
        )
        return ColumnLineage(
            name=name,
            sources=tuple(sorted(f"{view}.{column}" for view, column in sources)),
            classification=classification,
        )
