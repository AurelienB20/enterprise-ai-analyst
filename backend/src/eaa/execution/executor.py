"""Run a validated query as eaa_reader, read-only, with hard limits.

Every query gets its own connection and its own READ ONLY transaction, which is always
rolled back: no session state survives from one query to the next. Inside the
transaction the limits are set again with SET LOCAL, whatever the role defaults say.
Rows are read through a server-side cursor, at most ``max_rows + 1`` of them, so a huge
result never reaches Python and truncation is detected exactly.

Synchronous on purpose: one short query at a time per request, run in a worker thread
by the API. (psycopg's async mode also needs a selector event loop on Windows, where
this project is developed.)
"""

import logging
import time
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql

from eaa.sql_security.validator import ValidatedQuery

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionLimits:
    timeout_ms: int = 5_000
    max_rows: int = 1_000
    work_mem_mb: int = 32

    def __post_init__(self) -> None:
        if not (0 < self.timeout_ms <= 60_000 and 0 < self.max_rows <= 100_000):
            raise ValueError("limits out of range")
        if not 0 < self.work_mem_mb <= 256:
            raise ValueError("work_mem out of range")


@dataclass(frozen=True)
class ResultColumn:
    name: str
    type_name: str


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[ResultColumn, ...]
    rows: tuple[tuple[Any, ...], ...]
    truncated: bool  # more rows existed than max_rows
    duration_ms: float


class ExecutionError(Exception):
    """The database refused or failed the query. ``message`` is safe to show."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message


class QueryTimeoutError(ExecutionError):
    def __init__(self, timeout_ms: int) -> None:
        super().__init__("timeout", f"The query took longer than {timeout_ms} ms.")


class PermissionDeniedError(ExecutionError):
    """The database role refused: the validator should have caught it first."""

    def __init__(self) -> None:
        super().__init__("permission_denied", "The database refused access.")


class ReadOnlyExecutor:
    def __init__(self, reader_url: str, limits: ExecutionLimits | None = None) -> None:
        self._url = reader_url
        self.limits = limits or ExecutionLimits()

    def execute(self, query: ValidatedQuery) -> QueryResult:
        return self._run(query.sql)

    def _run(self, statement: str) -> QueryResult:
        """Run ``statement`` under the limits. Only ``execute`` is public: tests call this
        directly to check that the database layer holds without the validator."""
        limits = self.limits
        started = time.perf_counter()
        try:
            with psycopg.connect(self._url, autocommit=False) as connection:
                connection.read_only = True
                try:
                    return self._run_in_transaction(connection, statement, started)
                finally:
                    connection.rollback()
        except psycopg.errors.QueryCanceled:
            logger.warning("Query cancelled after %d ms", limits.timeout_ms)
            raise QueryTimeoutError(limits.timeout_ms) from None
        except psycopg.errors.InsufficientPrivilege:
            # The validator lets nothing through that the role refuses: this is a signal.
            logger.error("The database refused a query that passed validation")
            raise PermissionDeniedError from None
        except psycopg.errors.ReadOnlySqlTransaction:
            logger.error("A write reached the read-only transaction")
            raise PermissionDeniedError from None
        except psycopg.Error as error:
            message = error.diag.message_primary or type(error).__name__
            raise ExecutionError("database_error", message) from None

    def _run_in_transaction(
        self, connection: psycopg.Connection, statement: str, started: float
    ) -> QueryResult:
        limits = self.limits
        with connection.cursor() as setup:
            for setting, value in (
                ("statement_timeout", f"{limits.timeout_ms}ms"),
                ("lock_timeout", "1s"),
                ("idle_in_transaction_session_timeout", f"{limits.timeout_ms + 5_000}ms"),
                ("work_mem", f"{limits.work_mem_mb}MB"),
                ("search_path", "analytics"),
            ):
                setup.execute(
                    sql.SQL("SET LOCAL {} = {}").format(sql.Identifier(setting), sql.Literal(value))
                )
        with connection.cursor(name="analysis") as cursor:
            cursor.execute(statement)  # validated, regenerated SQL
            rows = cursor.fetchmany(limits.max_rows + 1)
            description = cursor.description or []
            columns = tuple(
                ResultColumn(column.name, _type_name(connection, column.type_code))
                for column in description
            )
        truncated = len(rows) > limits.max_rows
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        logger.info(
            "Query ran",
            extra={
                "rows": min(len(rows), limits.max_rows),
                "truncated": truncated,
                "duration_ms": duration_ms,
            },
        )
        return QueryResult(
            columns=columns,
            rows=tuple(tuple(row) for row in rows[: limits.max_rows]),
            truncated=truncated,
            duration_ms=duration_ms,
        )


def _type_name(connection: psycopg.Connection, oid: int) -> str:
    info = connection.adapters.types.get(oid)
    return info.name if info is not None else str(oid)
