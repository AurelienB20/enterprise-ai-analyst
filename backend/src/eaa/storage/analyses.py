"""The audit trail of analyses (app.analyses), as eaa_app.

What is recorded: the question, every proposed SQL with its outcome, the SQL that ran,
counts, timings, tokens and cost. What is not: the result rows.
"""

import uuid
from dataclasses import asdict
from decimal import Decimal
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
    "insight_status", "insight_numbers_checked", "explanation_ms", "masked_personal_data",
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
                    input_tokens, output_tokens, cache_read_tokens, cost_usd,
                    insight_status, insight_numbers_checked, explanation_ms,
                    masked_personal_data
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s
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
                    analysis.insight.status if analysis.insight else None,
                    analysis.insight.numbers_checked if analysis.insight else None,
                    analysis.explanation_ms if analysis.insight else None,
                    list(analysis.masked_personal_data),
                ),
            )

    def get(self, analysis_id: uuid.UUID) -> dict[str, Any] | None:
        with psycopg.connect(self._url, row_factory=dict_row) as connection:
            return connection.execute(
                f"SELECT {', '.join(COLUMNS)} FROM app.analyses WHERE id = %s",  # noqa: S608
                (analysis_id,),
            ).fetchone()

    def spent_today(self) -> Decimal:
        """Cost of the analyses recorded since midnight UTC."""
        with psycopg.connect(self._url) as connection:
            row = connection.execute(
                "SELECT coalesce(sum(cost_usd), 0) FROM app.analyses "
                "WHERE created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"
            ).fetchone()
        return Decimal(row[0]) if row else Decimal(0)

    def stats(self, days: int) -> dict[str, Any]:
        """Aggregates over the last ``days`` days: counts, rates, latency, cost. Never a
        question or a value from a result."""
        with psycopg.connect(self._url, row_factory=dict_row) as connection:
            row = connection.execute(STATS_SQL, {"days": days}).fetchone()
        return dict(row) if row else {}


STATS_SQL = """
WITH recent AS (
    SELECT * FROM app.analyses WHERE created_at >= now() - make_interval(days => %(days)s)
),
attempts AS (
    SELECT a->>'outcome' AS outcome, a->>'message' AS message
    FROM recent, jsonb_array_elements(recent.attempts) a
)
SELECT
    (SELECT count(*) FROM recent) AS analyses,
    (SELECT count(*) FROM recent WHERE status = 'answered') AS answered,
    (SELECT count(*) FROM recent WHERE status = 'declined') AS declined,
    (SELECT count(*) FROM recent WHERE status = 'rejected') AS rejected,
    (SELECT count(*) FROM recent WHERE status = 'failed') AS failed,
    (SELECT count(*) FROM attempts) AS sql_proposals,
    (SELECT count(*) FROM attempts WHERE outcome = 'rejected') AS sql_rejected_by_validator,
    (SELECT count(*) FROM attempts WHERE outcome = 'failed'
        AND message LIKE 'The query took longer%%') AS sql_timeouts,
    (SELECT count(*) FROM recent WHERE error_kind = 'permission_denied') AS permission_violations,
    (SELECT count(*) FROM recent WHERE error_kind = 'llm_error') AS llm_errors,
    (SELECT count(*) FROM recent WHERE insight_status = 'verified') AS explanations_verified,
    (SELECT count(*) FROM recent WHERE insight_status = 'fallback') AS explanations_withheld,
    (SELECT count(*) FROM recent WHERE cardinality(masked_personal_data) > 0)
        AS questions_with_personal_data_masked,
    (SELECT coalesce(sum(input_tokens + cache_read_tokens), 0) FROM recent) AS input_tokens,
    (SELECT coalesce(sum(output_tokens), 0) FROM recent) AS output_tokens,
    (SELECT coalesce(sum(cost_usd), 0) FROM recent) AS cost_usd,
    (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY total_ms) FROM recent) AS latency_p50_ms,
    (SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms) FROM recent) AS latency_p95_ms
"""
