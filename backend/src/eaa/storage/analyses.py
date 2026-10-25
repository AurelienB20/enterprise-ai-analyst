"""The audit trail of analyses (app.analyses), as eaa_app.

What is recorded: the question, every proposed SQL with its outcome, the SQL that ran,
counts, timings, tokens and cost. What is not: the result rows.
"""

import uuid
from dataclasses import asdict
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from eaa.orchestrator.pipeline import Analysis

COLUMNS = (
    "id", "created_at", "correlation_id", "question", "status", "model", "attempts",
    "executed_sql", "views", "row_count", "truncated", "assumptions", "ambiguities",
    "explanation", "error_kind", "error_message", "generation_ms", "execution_ms",
    "total_ms", "input_tokens", "output_tokens", "cache_read_tokens", "cost_usd",
)  # fmt: skip


class AnalysisStore:
    def __init__(self, app_url: str) -> None:
        self._url = app_url

    def record(self, analysis: Analysis, correlation_id: str | None) -> None:
        proposal = analysis.proposal
        result = analysis.result
        error_message = analysis.error_message
        if analysis.declined is not None:
            error_message = analysis.declined.message
        with psycopg.connect(self._url) as connection:
            connection.execute(
                """
                INSERT INTO app.analyses (
                    id, correlation_id, question, status, model, attempts, executed_sql,
                    views, row_count, truncated, assumptions, ambiguities, explanation,
                    error_kind, error_message, generation_ms, execution_ms, total_ms,
                    input_tokens, output_tokens, cache_read_tokens, cost_usd
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                """,
                (
                    analysis.id,
                    correlation_id,
                    analysis.question,
                    analysis.status,
                    analysis.model,
                    Jsonb([asdict(attempt) for attempt in analysis.attempts]),
                    analysis.executed.sql if analysis.executed else None,
                    sorted(analysis.executed.views) if analysis.executed else [],
                    len(result.rows) if result else None,
                    result.truncated if result else None,
                    Jsonb(list(proposal.assumptions) if proposal else []),
                    Jsonb(list(proposal.ambiguities) if proposal else []),
                    proposal.explanation if proposal else None,
                    analysis.declined.reason if analysis.declined else analysis.error_kind,
                    error_message,
                    analysis.generation_ms,
                    analysis.execution_ms,
                    analysis.total_ms,
                    analysis.usage.input_tokens,
                    analysis.usage.output_tokens,
                    analysis.usage.cache_read_tokens,
                    analysis.cost_usd,
                ),
            )

    def get(self, analysis_id: uuid.UUID) -> dict[str, Any] | None:
        with psycopg.connect(self._url, row_factory=dict_row) as connection:
            return connection.execute(
                f"SELECT {', '.join(COLUMNS)} FROM app.analyses WHERE id = %s",  # noqa: S608
                (analysis_id,),
            ).fetchone()
