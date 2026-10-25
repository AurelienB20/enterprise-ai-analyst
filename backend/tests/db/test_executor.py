"""The read-only executor, and defense in depth: each attack the corpus marks with the
"db" layer must fail in the database even when the validator is skipped."""

import pytest

from eaa.execution.executor import (
    ExecutionError,
    ExecutionLimits,
    QueryTimeoutError,
    ReadOnlyExecutor,
)
from eaa.semantic.model import load
from eaa.sql_security.validator import SQLValidator
from tests.sql_corpus import ATTACKS, LEGITIMATE, Attack

pytestmark = pytest.mark.db

DB_LAYER_ATTACKS = {name: a for name, a in ATTACKS.items() if "db" in a.layers}


@pytest.fixture(scope="module")
def validator() -> SQLValidator:
    return SQLValidator(load())


@pytest.fixture
def executor(reader_database_url: str) -> ReadOnlyExecutor:
    return ReadOnlyExecutor(reader_database_url, ExecutionLimits(timeout_ms=2_000, max_rows=500))


def canonical(rows: tuple[tuple[object, ...], ...]) -> list[str]:
    return sorted(repr(row) for row in rows)


@pytest.mark.parametrize("sql", LEGITIMATE.values(), ids=LEGITIMATE.keys())
def test_regenerated_sql_returns_what_the_original_returns(
    validator: SQLValidator, executor: ReadOnlyExecutor, sql: str
) -> None:
    validated = executor.execute(validator.validate(sql))
    original = executor._run(sql)

    assert validated.rows
    assert [c.name for c in validated.columns] == [c.name for c in original.columns]
    assert canonical(validated.rows) == canonical(original.rows)


@pytest.mark.parametrize("attack", DB_LAYER_ATTACKS.values(), ids=DB_LAYER_ATTACKS.keys())
def test_the_database_layer_stops_the_attack_without_the_validator(
    executor: ReadOnlyExecutor, attack: Attack
) -> None:
    with pytest.raises(ExecutionError):
        executor._run(attack.sql)


def test_personal_data_is_refused_as_a_permission_error(executor: ReadOnlyExecutor) -> None:
    with pytest.raises(ExecutionError) as raised:
        executor._run("SELECT email FROM sales.customer_contacts")

    assert raised.value.kind == "permission_denied"


def test_the_timeout_is_enforced_inside_the_transaction(reader_database_url: str) -> None:
    executor = ReadOnlyExecutor(reader_database_url, ExecutionLimits(timeout_ms=200))

    with pytest.raises(QueryTimeoutError):
        executor._run("SELECT pg_sleep(2)")


def test_limits_are_set_again_in_every_transaction(executor: ReadOnlyExecutor) -> None:
    result = executor._run(
        "SELECT current_setting('statement_timeout'), current_setting('search_path'), "
        "current_setting('transaction_read_only'), current_setting('work_mem')"
    )

    assert result.rows == (("2s", "analytics", "on", "32MB"),)


def test_no_session_state_survives_a_query(executor: ReadOnlyExecutor) -> None:
    # Even if a query changed a session setting, the next one starts from scratch.
    executor._run("SELECT set_config('work_mem', '1MB', false)")

    assert executor._run("SELECT current_setting('work_mem')").rows == (("32MB",),)


def test_results_are_capped_and_truncation_is_reported(reader_database_url: str) -> None:
    executor = ReadOnlyExecutor(reader_database_url, ExecutionLimits(max_rows=5))

    capped = executor._run("SELECT customer_id FROM customers ORDER BY customer_id")
    exact = executor._run("SELECT customer_id FROM customers ORDER BY customer_id LIMIT 5")

    assert capped.truncated and len(capped.rows) == 5
    assert not exact.truncated and capped.rows == exact.rows


def test_columns_carry_their_database_types(
    validator: SQLValidator, executor: ReadOnlyExecutor
) -> None:
    result = executor.execute(
        validator.validate("SELECT customer_id, region, created_at FROM customers LIMIT 1")
    )

    assert [(c.name, c.type_name) for c in result.columns] == [
        ("customer_id", "int4"),
        ("region", "text"),
        ("created_at", "date"),
    ]


def test_a_database_error_is_reported_without_leaking_internals(
    executor: ReadOnlyExecutor,
) -> None:
    with pytest.raises(ExecutionError) as raised:
        executor._run("SELECT 1 / 0")

    assert raised.value.kind == "database_error"
    assert raised.value.message == "division by zero"
