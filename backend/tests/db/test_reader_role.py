"""eaa_reader, the role that will run generated SQL, can read the analytics views and
nothing else, whatever the SQL says.

These tests check the database layer on its own: no validator is involved. Each
privilege check runs in a read-write transaction, so that it is the missing privilege,
not the read-only default, that stops the statement.
"""

import psycopg
import pytest

from eaa.semantic.model import load as load_model

pytestmark = pytest.mark.db


def setting(reader: psycopg.Connection, name: str) -> object:
    row = reader.execute(f"SHOW {name}").fetchone()
    assert row is not None
    return row[0]


def test_the_reader_sees_every_analytics_view(reader: psycopg.Connection) -> None:
    for view in load_model().views:
        row = reader.execute(f"SELECT count(*) FROM analytics.{view.name}").fetchone()  # noqa: S608
        assert row is not None and row[0] > 0, view.name


def test_the_reader_session_defaults(reader: psycopg.Connection) -> None:
    assert setting(reader, "default_transaction_read_only") == "on"
    assert setting(reader, "statement_timeout") == "10s"
    assert setting(reader, "search_path") == "analytics"
    # Unqualified names resolve to the views, not to the raw tables.
    assert reader.execute("SELECT count(*) FROM customers").fetchone() is not None


@pytest.mark.parametrize(
    "table",
    ["customers", "customer_contacts", "orders", "order_items", "invoices", "dataset_anomalies"],
)
def test_the_raw_tables_are_out_of_reach(reader: psycopg.Connection, table: str) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        reader.execute(f"SELECT * FROM sales.{table} LIMIT 1")  # noqa: S608


@pytest.mark.parametrize(
    "statement",
    [
        # analytics.customers is a simple, automatically updatable view: only the
        # missing privilege stops these three from writing through to sales.customers.
        "INSERT INTO analytics.customers (customer_id) VALUES (0)",
        "UPDATE analytics.customers SET region = 'x'",
        "DELETE FROM analytics.customers",
        "CREATE TABLE analytics.exfiltration (x int)",
        "CREATE TABLE public.exfiltration (x int)",
        "CREATE TEMP TABLE exfiltration (x int)",
        "DROP VIEW analytics.customers",
        "TRUNCATE sales.customers",
        "SELECT pg_read_file('/etc/passwd')",
        "COPY (SELECT 1) TO PROGRAM 'id'",
        "COPY (SELECT 1) TO '/tmp/exfiltration.csv'",
        "CREATE FUNCTION analytics.f() RETURNS int LANGUAGE sql AS 'SELECT 1'",
    ],
)
def test_writes_and_server_access_are_refused_even_in_read_write(
    reader: psycopg.Connection, statement: str
) -> None:
    reader.execute("BEGIN READ WRITE")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        reader.execute(statement)


def test_by_default_every_transaction_is_read_only(reader: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        reader.execute("CREATE TEMP TABLE exfiltration (x int)")
