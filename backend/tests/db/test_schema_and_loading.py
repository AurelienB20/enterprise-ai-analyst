from datetime import date

import psycopg
import pytest
from alembic import command

from eaa.synthetic.generator import Dataset, generate
from eaa.synthetic.loader import DatasetAlreadyLoadedError, load
from tests.db.conftest import alembic_config, load_committed_dataset

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return generate(seed=42, scale="small")


def scalar(connection: psycopg.Connection, query: str) -> object:
    row = connection.execute(query).fetchone()
    assert row is not None
    return row[0]


def test_the_database_is_utf8(connection: psycopg.Connection) -> None:
    assert scalar(connection, "SELECT pg_encoding_to_char(encoding) FROM pg_database "
                  "WHERE datname = current_database()") == "UTF8"  # fmt: skip


def test_migrations_go_down_and_up_again(migrated_database: str) -> None:
    config = alembic_config(migrated_database)
    command.downgrade(config, "base")
    with psycopg.connect(migrated_database) as conn:
        assert scalar(conn, "SELECT to_regnamespace('sales')") is None
    command.upgrade(config, "head")
    with psycopg.connect(migrated_database) as conn:
        assert scalar(conn, "SELECT count(*) FROM pg_tables WHERE schemaname = 'sales'") == 14
        assert scalar(conn, "SELECT count(*) FROM pg_views WHERE schemaname = 'analytics'") == 10
    # The other database tests expect the committed dataset.
    load_committed_dataset(migrated_database)


def test_the_dataset_loads_with_every_constraint_satisfied(
    empty_connection: psycopg.Connection, dataset: Dataset
) -> None:
    load(empty_connection, dataset)

    for table in dataset.tables.values():
        count = scalar(empty_connection, f"SELECT count(*) FROM sales.{table.name}")  # noqa: S608
        assert count == len(table.rows), table.name
    assert scalar(empty_connection, "SELECT reference_date FROM sales.dataset_metadata") == date(
        2026, 9, 30
    )


def test_sql_totals_match_the_generator(
    empty_connection: psycopg.Connection, dataset: Dataset
) -> None:
    load(empty_connection, dataset)

    expected = sum(row[5] for row in dataset.tables["invoices"].rows)  # type: ignore[misc]
    assert scalar(empty_connection, "SELECT sum(amount_excl_vat) FROM sales.invoices") == expected
    mismatches = scalar(
        empty_connection,
        """
        SELECT count(*) FROM sales.invoices i
        JOIN (SELECT order_id, sum(quantity * unit_price - discount_amount) AS net
              FROM sales.order_items GROUP BY order_id) l ON l.order_id = i.order_id
        WHERE l.net <> i.amount_excl_vat
        """,
    )
    assert mismatches == 0


def test_a_second_load_is_refused_unless_replace_is_asked(
    empty_connection: psycopg.Connection, dataset: Dataset
) -> None:
    load(empty_connection, dataset)

    with pytest.raises(DatasetAlreadyLoadedError):
        load(empty_connection, dataset)

    other = generate(seed=7, scale="small")
    load(empty_connection, other, replace=True)
    assert scalar(empty_connection, "SELECT seed FROM sales.dataset_metadata") == 7
    assert scalar(empty_connection, "SELECT count(*) FROM sales.orders") == len(
        other.tables["orders"].rows
    )


def test_constraints_reject_inconsistent_rows(empty_connection: psycopg.Connection) -> None:
    empty_connection.execute("INSERT INTO sales.categories VALUES (1, 'Test')")
    empty_connection.execute("INSERT INTO sales.suppliers VALUES (1, 'S', 'FR', 7)")
    empty_connection.execute(
        "INSERT INTO sales.products VALUES (1, 'SKU', 'P', 1, 1, 10, 5, '2024-01-01')"
    )
    empty_connection.execute(
        "INSERT INTO sales.customers VALUES (1, 'C', 'FR', 'Western Europe', 'Retail', "
        "'SMB', 30, '2024-01-01')"
    )
    empty_connection.execute("INSERT INTO sales.orders VALUES (1, 1, '2024-02-01', 'delivered')")

    with pytest.raises(psycopg.errors.CheckViolation), empty_connection.transaction():
        # The discount is larger than the line.
        empty_connection.execute("INSERT INTO sales.order_items VALUES (1, 1, 1, 2, 10, 5, 25)")
    with pytest.raises(psycopg.errors.CheckViolation), empty_connection.transaction():
        empty_connection.execute("INSERT INTO sales.orders VALUES (2, 1, '2024-02-01', 'lost')")
    with pytest.raises(psycopg.errors.ForeignKeyViolation), empty_connection.transaction():
        empty_connection.execute(
            "INSERT INTO sales.orders VALUES (3, 999, '2024-02-01', 'pending')"
        )
