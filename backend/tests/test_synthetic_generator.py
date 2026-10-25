"""Invariants of the generated dataset, checked in Python without a database."""

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

import pytest

from eaa.synthetic.generator import (
    REFERENCE_DATE,
    SCALES,
    START_DATE,
    Dataset,
    generate,
    money,
)


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return generate(seed=42, scale="small")


def rows(dataset: Dataset, table: str) -> list[tuple[object, ...]]:
    return dataset.tables[table].rows


def test_the_same_seed_gives_the_same_rows(dataset: Dataset) -> None:
    assert generate(seed=42, scale="small").digest() == dataset.digest()


def test_another_seed_gives_other_rows(dataset: Dataset) -> None:
    assert generate(seed=43, scale="small").digest() != dataset.digest()


def test_row_counts_follow_the_scale(dataset: Dataset) -> None:
    scale = SCALES["small"]
    assert len(rows(dataset, "customers")) == scale.customers
    assert len(rows(dataset, "products")) == scale.products
    assert len(rows(dataset, "suppliers")) == scale.suppliers
    # The one-off big order (A7) comes on top of the regular ones.
    assert len(rows(dataset, "orders")) == scale.orders + 1
    assert len(rows(dataset, "dataset_anomalies")) == 8


def test_every_row_has_one_value_per_column(dataset: Dataset) -> None:
    for table in dataset.tables.values():
        assert all(len(row) == len(table.columns) for row in table.rows), table.name


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("orders", 2),
        ("invoices", 3),
        ("credit_notes", 3),
        ("payments", 2),
        ("supplier_deliveries", 4),
        ("inventory_snapshots", 0),
    ],
)
def test_no_event_happens_outside_the_dataset_period(
    dataset: Dataset, table: str, column: int
) -> None:
    dates = [row[column] for row in rows(dataset, table)]
    assert min(dates) >= START_DATE  # type: ignore[type-var, operator]
    assert max(dates) <= REFERENCE_DATE  # type: ignore[type-var, operator]


def test_customers_only_order_after_they_exist(dataset: Dataset) -> None:
    created = {row[0]: row[7] for row in rows(dataset, "customers")}
    assert all(row[2] >= created[row[1]] for row in rows(dataset, "orders"))  # type: ignore[operator]


def test_names_are_unique_and_contacts_unreachable(dataset: Dataset) -> None:
    names = [row[1] for row in rows(dataset, "customers")]
    assert len(set(names)) == len(names)
    for row in rows(dataset, "customer_contacts"):
        assert str(row[4]).endswith(".example")
        assert str(row[5]).startswith("+1-555-01")


def test_order_lines_are_consistent(dataset: Dataset) -> None:
    pairs = Counter((row[1], row[2]) for row in rows(dataset, "order_items"))
    assert max(pairs.values()) == 1
    for _, _, _, quantity, price, _, discount in rows(dataset, "order_items"):
        assert 0 <= discount <= quantity * price  # type: ignore[operator]


def test_only_shipped_or_delivered_orders_are_invoiced_once(dataset: Dataset) -> None:
    invoiced = Counter(row[2] for row in rows(dataset, "invoices"))
    for order_id, _, _, status in rows(dataset, "orders"):
        expected = 1 if status in ("shipped", "delivered") else 0
        assert invoiced[order_id] == expected


def test_invoice_amounts_match_their_lines_and_vat(dataset: Dataset) -> None:
    net: dict[object, Decimal] = defaultdict(Decimal)
    for _, order_id, _, quantity, price, _, discount in rows(dataset, "order_items"):
        net[order_id] += quantity * price - discount  # type: ignore[operator]
    country = {row[0]: row[2] for row in rows(dataset, "customers")}
    customer_of = {row[0]: row[1] for row in rows(dataset, "orders")}
    for row in rows(dataset, "invoices"):
        _, _, order_id, invoice_date, due_date, excl, vat, incl, _ = row
        assert excl == net[order_id]
        assert vat == (Decimal("0.200") if country[customer_of[order_id]] == "FR" else 0)
        assert incl == money(excl * (1 + vat))  # type: ignore[operator]
        assert due_date >= invoice_date  # type: ignore[operator]


def test_payments_and_credit_notes_never_exceed_the_invoice(dataset: Dataset) -> None:
    invoices = {row[0]: row for row in rows(dataset, "invoices")}
    paid: dict[object, Decimal] = defaultdict(Decimal)
    for _, invoice_id, payment_date, amount, _ in rows(dataset, "payments"):
        assert payment_date >= invoices[invoice_id][3]  # type: ignore[operator]
        paid[invoice_id] += amount  # type: ignore[operator]
    credited: dict[object, Decimal] = defaultdict(Decimal)
    for _, invoice_id, _, _, amount, _ in rows(dataset, "credit_notes"):
        credited[invoice_id] += amount  # type: ignore[operator]
    for invoice_id, row in invoices.items():
        excl, vat, incl, status = row[5], row[6], row[7], row[8]
        assert credited[invoice_id] <= excl  # type: ignore[operator]
        owed = incl - money(credited[invoice_id] * (1 + vat))  # type: ignore[operator]
        assert paid[invoice_id] <= owed
        if status == "paid":
            assert paid[invoice_id] == owed
        elif status == "partially_paid":
            assert 0 < paid[invoice_id] < owed
        else:
            assert paid[invoice_id] == 0


def test_a_credit_note_credits_at_most_one_line_of_its_invoice(dataset: Dataset) -> None:
    order_of_invoice = {row[0]: row[2] for row in rows(dataset, "invoices")}
    line_net = {
        (row[1], row[2]): row[3] * row[4] - row[6]  # type: ignore[operator]
        for row in rows(dataset, "order_items")
    }
    credited: dict[tuple[object, object], Decimal] = defaultdict(Decimal)
    for _, invoice_id, product_id, _, amount, _ in rows(dataset, "credit_notes"):
        credited[(order_of_invoice[invoice_id], product_id)] += amount  # type: ignore[operator]

    assert credited
    for line, amount in credited.items():
        assert line in line_net
        assert amount <= line_net[line]


def test_august_is_the_quietest_month_and_volume_grows(dataset: Dataset) -> None:
    per_month = Counter((row[2].year, row[2].month) for row in rows(dataset, "orders"))  # type: ignore[attr-defined]
    for year in (2023, 2024, 2025):
        months = {m: per_month[(year, m)] for m in range(1, 13)}
        assert min(months, key=lambda m: months[m]) == 8
    per_year = Counter(row[2].year for row in rows(dataset, "orders"))  # type: ignore[attr-defined]
    assert per_year[2023] < per_year[2024] < per_year[2025]


def test_supplier_deliveries_are_dated_consistently(dataset: Dataset) -> None:
    for row in rows(dataset, "supplier_deliveries"):
        order_date, expected, delivered = row[4], row[5], row[6]
        assert expected >= order_date  # type: ignore[operator]
        assert delivered is None or order_date <= delivered <= REFERENCE_DATE  # type: ignore[operator]


def test_the_reference_date_is_recorded(dataset: Dataset) -> None:
    (metadata,) = rows(dataset, "dataset_metadata")
    assert metadata == (1, "2", 42, "small", START_DATE, date(2026, 9, 30))
