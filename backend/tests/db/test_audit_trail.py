"""The audit trail, written and read as eaa_app, and the separation between the roles."""

from decimal import Decimal

import psycopg
import pytest

from eaa.execution.executor import QueryResult, ResultColumn
from eaa.llm.sql_generator import Declined, QueryProposal, Usage
from eaa.orchestrator.pipeline import Analysis, Attempt
from eaa.sql_security.validator import ValidatedQuery
from eaa.storage.analyses import AnalysisStore

pytestmark = pytest.mark.db


def answered() -> Analysis:
    analysis = Analysis(question="Revenue by region?", model="test-model", status="answered")
    analysis.proposal = QueryProposal(
        "SELECT 1", ("sales_lines",), "Sums revenue.", ("All time.",), ("Or this year.",)
    )
    analysis.executed = ValidatedQuery("SELECT 1", frozenset({"sales_lines"}), frozenset())
    analysis.result = QueryResult(
        (ResultColumn("region", "text"), ResultColumn("revenue", "numeric")),
        (("Southern Europe", Decimal("99.99")),),
        truncated=False,
        duration_ms=2.0,
    )
    analysis.attempts = [
        Attempt("SELECT * FROM sales.customers", "rejected", "not an analytics view"),
        Attempt("SELECT 1", "accepted"),
    ]
    analysis.usage = Usage(calls=2, input_tokens=10, output_tokens=5, cache_read_tokens=100)
    analysis.cost_usd = 0.000123
    analysis.total_ms = 42.0
    return analysis


def test_an_analysis_is_recorded_without_its_result_rows(app_database_url: str) -> None:
    store = AnalysisStore(app_database_url)
    analysis = answered()

    store.record(analysis, correlation_id="req-1")
    row = store.get(analysis.id)

    assert row is not None
    assert row["status"] == "answered" and row["correlation_id"] == "req-1"
    assert row["views"] == ["sales_lines"] and row["row_count"] == 1
    assert row["attempts"] == [
        {
            "sql": "SELECT * FROM sales.customers",
            "outcome": "rejected",
            "message": "not an analytics view",
        },
        {"sql": "SELECT 1", "outcome": "accepted", "message": None},
    ]
    assert row["assumptions"] == ["All time."]
    assert row["cost_usd"] == Decimal("0.000123")
    # The values of the result are nowhere in the audit row.
    assert "Southern Europe" not in repr(row) and "99.99" not in repr(row)


def test_a_decline_is_recorded_with_its_reason(app_database_url: str) -> None:
    store = AnalysisStore(app_database_url)
    analysis = Analysis(question="Emails?", model="test-model", status="declined")
    analysis.declined = Declined("personal_data", "Emails are not available.")

    store.record(analysis, correlation_id=None)
    row = store.get(analysis.id)

    assert row is not None
    assert row["error_kind"] == "personal_data"
    assert row["error_message"] == "Emails are not available."


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT count(*) FROM analytics.sales_lines",
        "SELECT count(*) FROM sales.customer_contacts",
        "UPDATE app.analyses SET status = 'answered'",
        "DELETE FROM app.analyses",
    ],
)
def test_the_app_role_only_inserts_and_reads_its_trail(
    app_database_url: str, statement: str
) -> None:
    with (
        psycopg.connect(app_database_url) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute(statement)


def test_the_reader_cannot_read_the_audit_trail(reader_database_url: str) -> None:
    with (
        psycopg.connect(reader_database_url) as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        connection.execute("SELECT question FROM app.analyses")


def test_todays_spending_adds_up_recorded_costs(app_database_url: str) -> None:
    store = AnalysisStore(app_database_url)
    before = store.spent_today()

    store.record(answered(), correlation_id=None)

    assert store.spent_today() - before == Decimal("0.000123")
