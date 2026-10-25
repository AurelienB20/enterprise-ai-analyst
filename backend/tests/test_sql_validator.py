import pytest

from eaa.semantic.model import load
from eaa.sql_security.validator import Rejection, SQLRejectedError, SQLValidator
from tests.sql_corpus import ATTACKS, LEGITIMATE, Attack


@pytest.fixture(scope="module")
def validator() -> SQLValidator:
    return SQLValidator(load())


@pytest.mark.parametrize("sql", LEGITIMATE.values(), ids=LEGITIMATE.keys())
def test_legitimate_queries_are_accepted(validator: SQLValidator, sql: str) -> None:
    query = validator.validate(sql)

    assert query.views
    assert ";" not in query.sql


@pytest.mark.parametrize("attack", ATTACKS.values(), ids=ATTACKS.keys())
def test_attacks_are_rejected_for_the_right_reason(validator: SQLValidator, attack: Attack) -> None:
    with pytest.raises(SQLRejectedError) as raised:
        validator.validate(attack.sql)

    assert raised.value.reason == attack.rejection


def test_the_views_and_functions_used_are_reported(validator: SQLValidator) -> None:
    query = validator.validate(LEGITIMATE["top 10 customers"])

    assert query.views == {"sales_lines", "customers"}
    assert query.functions == {"SUM"}


def test_ctes_are_not_mistaken_for_tables(validator: SQLValidator) -> None:
    query = validator.validate(LEGITIMATE["biggest drop this quarter"])

    assert query.views == {"sales_lines", "dataset_info"}


def test_a_cte_cannot_launder_a_raw_table_name(validator: SQLValidator) -> None:
    # A CTE named like a raw table does not make the raw table reachable.
    with pytest.raises(SQLRejectedError) as raised:
        validator.validate(
            "WITH customer_contacts AS (SELECT 1 AS x) SELECT * FROM sales.customer_contacts"
        )
    assert raised.value.reason == Rejection.FORBIDDEN_TABLE


def test_what_runs_is_regenerated_without_comments(validator: SQLValidator) -> None:
    query = validator.validate("SELECT /* note */ COUNT(*) -- trailing\nFROM customers")

    assert "--" not in query.sql
    assert "note" not in query.sql
    assert query.sql == "SELECT COUNT(*) FROM customers"


def test_rejection_messages_name_the_problem(validator: SQLValidator) -> None:
    with pytest.raises(SQLRejectedError) as raised:
        validator.validate("SELECT * FROM sales.customer_contacts")

    assert "sales.customer_contacts" in raised.value.message
    assert "Allowed views" in raised.value.message


def test_the_corpus_covers_every_rejection_reason() -> None:
    assert {attack.rejection for attack in ATTACKS.values()} == set(Rejection)
