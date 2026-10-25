"""Each injected anomaly must be the clear answer to the question it was designed for.

Checked on seed 42 at both scales: the evaluation relies on these answers. Other seeds
usually, but not always, give the same answers (docs/data-model.md).
"""

from collections import defaultdict
from decimal import Decimal

import pytest

from eaa.synthetic.generator import CHURN_DATE, RETURNS_MONTH, UNPAID_FROM, ScaleName, generate
from tests.synthetic_facts import Q2_2026, Q3_2026, YTD_2025, YTD_2026, Facts, top


@pytest.fixture(scope="module", params=["small", "full"])
def facts(request: pytest.FixtureRequest) -> Facts:
    scale: ScaleName = request.param
    return Facts(generate(seed=42, scale=scale))


def test_a1_the_churned_key_account_has_the_largest_revenue_drop(facts: Facts) -> None:
    churned = facts.anomalies["A1_CHURNED_KEY_ACCOUNT"]
    before = facts.revenue_by("customer_id", *Q2_2026)
    after = facts.revenue_by("customer_id", *Q3_2026)
    drop = {k: after.get(k, Decimal(0)) - v for k, v in before.items()}

    assert top(drop, reverse=False) == churned  # type: ignore[arg-type]
    assert all(line.order_date < CHURN_DATE for line in facts.lines if line.customer_id == churned)


def test_a2_the_category_drop_is_the_largest_one_this_quarter(facts: Facts) -> None:
    growth = facts.growth_by("category_id", Q2_2026, Q3_2026)

    assert top(growth, reverse=False) == facts.anomalies["A2_CATEGORY_DROP"]
    assert growth[facts.anomalies["A2_CATEGORY_DROP"]] < -0.3


def test_a3_the_late_supplier_has_the_highest_share_of_late_deliveries(facts: Facts) -> None:
    late: dict[object, list[bool]] = defaultdict(list)
    for row in facts.dataset.tables["supplier_deliveries"].rows:
        if row[6] is not None:
            late[row[1]].append(row[6] > row[5])  # type: ignore[operator]
    share = {k: sum(v) / len(v) for k, v in late.items()}

    assert top(share) == facts.anomalies["A3_LATE_SUPPLIER"]
    assert share[facts.anomalies["A3_LATE_SUPPLIER"]] > 0.5


def test_a4_only_the_mispriced_product_sells_below_cost(facts: Facts) -> None:
    below_cost = {
        row[0]
        for row in facts.dataset.tables["products"].rows
        if row[6] > row[5]  # type: ignore[operator]
    }
    lines_below_cost = {
        row[2]
        for row in facts.dataset.tables["order_items"].rows
        if row[5] > row[4]  # type: ignore[operator]
    }

    assert below_cost == {facts.anomalies["A4_NEGATIVE_MARGIN"]}
    assert lines_below_cost == {facts.anomalies["A4_NEGATIVE_MARGIN"]}


def test_a5_southern_europe_grows_the_fastest(facts: Facts) -> None:
    growth = facts.growth_by("region", YTD_2025, YTD_2026)

    assert top(growth) == "Southern Europe"


def test_a6_the_unpaid_customer_has_the_largest_overdue_amount(facts: Facts) -> None:
    unpaid = facts.anomalies["A6_UNPAID_CUSTOMER"]
    invoices = {
        row[0]: row
        for row in facts.dataset.tables["invoices"].rows
        if facts.orders[row[2]][1] == unpaid and row[3] >= UNPAID_FROM  # type: ignore[operator]
    }
    paid_invoices = {row[1] for row in facts.dataset.tables["payments"].rows}

    assert top(facts.overdue_amount_by_customer()) == unpaid  # type: ignore[arg-type]
    assert invoices
    assert not paid_invoices & set(invoices)


def test_a7_the_one_off_order_is_by_far_the_largest(facts: Facts) -> None:
    totals: dict[object, Decimal] = defaultdict(Decimal)
    for row in facts.dataset.tables["order_items"].rows:
        totals[row[1]] += row[3] * row[4] - row[6]  # type: ignore[operator]
    ranked = sorted(totals.values(), reverse=True)

    assert top(totals) == facts.anomalies["A7_ONE_OFF_BIG_ORDER"]  # type: ignore[arg-type]
    assert ranked[0] > 2 * ranked[1]


def test_a8_the_returned_product_has_the_most_returns_that_month(facts: Facts) -> None:
    tables = facts.dataset.tables
    returned_invoices = {row[1] for row in tables["credit_notes"].rows if row[4] == "return"}
    order_of_invoice = {
        row[0]: row[2]
        for row in tables["invoices"].rows
        if row[3].replace(day=1) == RETURNS_MONTH  # type: ignore[attr-defined]
    }
    returns: dict[object, int] = defaultdict(int)
    returned_orders = {order_of_invoice[i] for i in returned_invoices if i in order_of_invoice}
    for row in tables["order_items"].rows:
        if row[1] in returned_orders:
            returns[row[2]] += 1

    assert top(returns) == facts.anomalies["A8_RETURNS_SPIKE"]
