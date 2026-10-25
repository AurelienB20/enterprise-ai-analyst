"""The analytics views against the semantic model, and every metric on hand-computed data."""

from collections import defaultdict
from decimal import Decimal

import psycopg
import pytest

from eaa.semantic.model import load as load_model
from eaa.synthetic.generator import generate

pytestmark = pytest.mark.db

# A tiny company, small enough to compute every metric by hand. Reference date 2026-09-30.
#   O1  C1 (FR) 2026-08-10 delivered  P1 2 x 100 - 20 discount = 180 (cost 2 x 60)
#                                     P2 4 x 50             = 200 (cost 4 x 20)
#       invoice I1 2026-08-11, due 2026-09-10, 380 + 20 % VAT = 456
#       credit note on P2: 40 (48 incl. VAT); paid 300 on 2026-09-20 -> owes 108, 20 days overdue
#   O2  C2 (DE) 2026-09-25 pending    P1 1 x 100: not invoiced, not revenue
#   O3  C2 (DE) 2026-05-02 cancelled  P2 10 x 50: not revenue
#   O4  C2 (DE) 2026-03-01 delivered  P1 1 x 95 (cost 55); invoice I2 due 2026-04-01, 0 % VAT,
#       paid 95 on 2026-04-11 -> settled 10 days late
#   O5  C3 (FR) 2026-05-15 delivered  P2 1 x 50 (cost 20); invoice I3 due 2026-06-14, 60 incl.
#       VAT, unpaid -> 108 days overdue. C3 ordered 91-180 days ago only: became inactive.
#   Deliveries: D1 4 days late, D2 one day early, D3 missing 10 days after its expected
#   date, D4 expected after the reference date (not due).
TINY_COMPANY = """
INSERT INTO sales.dataset_metadata (id, generator_version, seed, scale, start_date, reference_date)
VALUES (1, 'hand', 0, 'tiny', '2026-01-01', '2026-09-30');
INSERT INTO sales.categories VALUES (1, 'Lighting');
INSERT INTO sales.suppliers VALUES (1, 'Supplier One', 'DE', 10);
INSERT INTO sales.products VALUES
    (1, 'P-1', 'Lamp', 1, 1, 100, 60, '2025-01-01'),
    (2, 'P-2', 'Bulb', 1, 1, 50, 20, '2025-01-01');
INSERT INTO sales.customers VALUES
    (1, 'Customer One SAS', 'FR', 'Western Europe', 'Retail', 'SMB', 30, '2024-01-01'),
    (2, 'Customer Two GmbH', 'DE', 'Central Europe', 'Retail', 'SMB', 30, '2024-01-01'),
    (3, 'Customer Three SAS', 'FR', 'Western Europe', 'Retail', 'SMB', 30, '2024-01-01');
INSERT INTO sales.orders VALUES
    (1, 1, '2026-08-10', 'delivered'),
    (2, 2, '2026-09-25', 'pending'),
    (3, 2, '2026-05-02', 'cancelled'),
    (4, 2, '2026-03-01', 'delivered'),
    (5, 3, '2026-05-15', 'delivered');
INSERT INTO sales.order_items VALUES
    (1, 1, 1, 2, 100, 60, 20),
    (2, 1, 2, 4, 50, 20, 0),
    (3, 2, 1, 1, 100, 60, 0),
    (4, 3, 2, 10, 50, 20, 0),
    (5, 4, 1, 1, 95, 55, 0),
    (6, 5, 2, 1, 50, 20, 0);
INSERT INTO sales.invoices VALUES
    (1, 'I-1', 1, '2026-08-11', '2026-09-10', 380, 0.200, 456, 'partially_paid'),
    (2, 'I-2', 4, '2026-03-02', '2026-04-01', 95, 0, 95, 'paid'),
    (3, 'I-3', 5, '2026-05-15', '2026-06-14', 50, 0.200, 60, 'open');
INSERT INTO sales.credit_notes
    (id, invoice_id, product_id, credit_note_date, amount_excl_vat, reason)
VALUES (1, 1, 2, '2026-08-20', 40, 'return');
INSERT INTO sales.payments VALUES
    (1, 1, '2026-09-20', 300, 'bank_transfer'),
    (2, 2, '2026-04-11', 95, 'card');
INSERT INTO sales.supplier_deliveries VALUES
    (1, 1, 1, 10, '2026-08-20', '2026-09-01', '2026-09-05'),
    (2, 1, 1, 10, '2026-08-30', '2026-09-10', '2026-09-09'),
    (3, 1, 2, 10, '2026-09-05', '2026-09-20', NULL),
    (4, 1, 2, 10, '2026-09-25', '2026-10-05', NULL);
"""

EXPECTED_METRICS = {
    "net_revenue": Decimal(485),
    "gross_margin": Decimal(210),
    "gross_margin_rate": Decimal(210) / Decimal(485),
    "invoiced_orders": 3,
    "average_order_value": Decimal(485) / Decimal(3),
    "cancellation_rate": Decimal("0.2"),
    "active_customers": 2,
    "overdue_amount": Decimal(168),
    "overdue_invoice_rate": Decimal(2) / Decimal(3),
    "average_days_paid_late": Decimal(10),
    "late_delivery_rate": Decimal(2) / Decimal(3),
}


def fetch_all(connection: psycopg.Connection, query: str) -> list[tuple[object, ...]]:
    return connection.execute(query).fetchall()


def test_views_match_the_semantic_model_exactly(connection: psycopg.Connection) -> None:
    rows = fetch_all(
        connection,
        """
        SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod)
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'analytics' AND a.attnum > 0 AND NOT a.attisdropped
        ORDER BY c.relname, a.attnum
        """,
    )
    in_database = {(str(view), str(column)): str(type_) for view, column, type_ in rows}
    documented = {
        (view.name, column.name): column.type
        for view in load_model().views
        for column in view.columns
    }

    assert in_database == documented


def test_every_metric_matches_its_hand_computed_value(
    empty_connection: psycopg.Connection,
) -> None:
    empty_connection.execute(TINY_COMPANY)
    metrics = load_model().metrics
    assert set(EXPECTED_METRICS) == {metric.name for metric in metrics}

    for metric in metrics:
        (value,) = fetch_all(
            empty_connection,
            f"SELECT {metric.expression} FROM analytics.{metric.view}",  # noqa: S608
        )[0]
        expected = EXPECTED_METRICS[metric.name]
        assert value == pytest.approx(expected, abs=Decimal("1e-9")), metric.name


def test_invoice_and_customer_details_on_hand_computed_data(
    empty_connection: psycopg.Connection,
) -> None:
    empty_connection.execute(TINY_COMPANY)

    invoices = fetch_all(
        empty_connection,
        "SELECT invoice_id, outstanding_amount, is_overdue, days_overdue, days_paid_late "
        "FROM analytics.invoices ORDER BY invoice_id",
    )
    assert invoices == [
        (1, Decimal("108.00"), True, 20, None),
        (2, Decimal("0.00"), False, None, 10),
        (3, Decimal("60.00"), True, 108, None),
    ]
    activity = fetch_all(
        empty_connection,
        "SELECT customer_id, is_active, became_inactive, net_revenue_last_12_months "
        "FROM analytics.customer_activity ORDER BY customer_id",
    )
    assert activity == [
        (1, True, False, Decimal(340)),
        (2, True, False, Decimal(95)),
        (3, False, True, Decimal(50)),
    ]
    credited = fetch_all(
        empty_connection,
        "SELECT product_id, credited_amount, net_revenue FROM analytics.sales_lines "
        "WHERE order_id = 1 ORDER BY product_id",
    )
    assert credited == [(1, Decimal(0), Decimal(180)), (2, Decimal(40), Decimal(160))]


def test_net_revenue_on_the_generated_data_matches_python(
    connection: psycopg.Connection,
) -> None:
    dataset = generate(seed=42, scale="small")
    tables = dataset.tables
    invoice_year = {row[2]: row[3].year for row in tables["invoices"].rows}  # type: ignore[attr-defined]
    year_of_invoice = {row[0]: row[3].year for row in tables["invoices"].rows}  # type: ignore[attr-defined]
    expected: dict[int, Decimal] = defaultdict(Decimal)
    for _, order_id, _, quantity, price, _, discount in tables["order_items"].rows:
        if order_id in invoice_year:
            expected[invoice_year[order_id]] += quantity * price - discount  # type: ignore[operator]
    for row in tables["credit_notes"].rows:
        expected[year_of_invoice[row[1]]] -= row[4]  # type: ignore[operator]

    rows = fetch_all(
        connection,
        "SELECT extract(year FROM invoice_date)::int, sum(net_revenue) "
        "FROM analytics.sales_lines GROUP BY 1 ORDER BY 1",
    )

    assert dict(rows) == dict(expected)  # type: ignore[arg-type]
