"""Facts computed from a generated dataset in plain Python, independently of SQL.

The anomaly tests use them to check that every injected anomaly is the clear answer to
the question it was designed for.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from eaa.synthetic.generator import REFERENCE_DATE, Dataset, money


@dataclass(frozen=True)
class Line:
    order_date: date
    customer_id: int
    region: str
    category_id: int
    product_id: int
    net: Decimal


class Facts:
    def __init__(self, dataset: Dataset) -> None:
        self.dataset = dataset
        rows = {name: table.rows for name, table in dataset.tables.items()}
        self.anomalies = {str(r[0]): r[3] for r in rows["dataset_anomalies"]}
        customers = {r[0]: r for r in rows["customers"]}
        products = {r[0]: r for r in rows["products"]}
        orders = {r[0]: r for r in rows["orders"]}
        self.orders = orders
        self.lines: list[Line] = []
        for _, order_id, product_id, quantity, price, _, discount in rows["order_items"]:
            order = orders[order_id]
            if order[3] == "cancelled":
                continue
            customer = customers[order[1]]
            self.lines.append(
                Line(
                    order_date=order[2],  # type: ignore[arg-type]
                    customer_id=order[1],  # type: ignore[arg-type]
                    region=customer[3],  # type: ignore[arg-type]
                    category_id=products[product_id][3],  # type: ignore[arg-type]
                    product_id=product_id,  # type: ignore[arg-type]
                    net=quantity * price - discount,  # type: ignore[operator]
                )
            )

    def revenue_by(self, key: str, start: date, end: date) -> dict[object, Decimal]:
        totals: dict[object, Decimal] = defaultdict(Decimal)
        for line in self.lines:
            if start <= line.order_date <= end:
                totals[getattr(line, key)] += line.net
        return dict(totals)

    def growth_by(
        self, key: str, before: tuple[date, date], after: tuple[date, date]
    ) -> dict[object, float]:
        old = self.revenue_by(key, *before)
        new = self.revenue_by(key, *after)
        return {k: float(new.get(k, Decimal(0)) / v) - 1 for k, v in old.items() if v > 0}

    def overdue_invoices_by_customer(self) -> dict[object, int]:
        counts: dict[object, int] = defaultdict(int)
        for row in self.dataset.tables["invoices"].rows:
            order_id, due_date, status = row[2], row[4], row[8]
            if status != "paid" and due_date < REFERENCE_DATE:  # type: ignore[operator]
                counts[self.orders[order_id][1]] += 1
        return dict(counts)

    def overdue_amount_by_customer(self) -> dict[object, Decimal]:
        """Outstanding amount (incl. VAT, net of credit notes and payments) past due date."""
        tables = self.dataset.tables
        paid: dict[object, Decimal] = defaultdict(Decimal)
        for row in tables["payments"].rows:
            paid[row[1]] += row[3]  # type: ignore[operator]
        credited: dict[object, Decimal] = defaultdict(Decimal)
        vat = {row[0]: row[6] for row in tables["invoices"].rows}
        for row in tables["credit_notes"].rows:
            credited[row[1]] += money(row[3] * (1 + vat[row[1]]))  # type: ignore[operator]
        totals: dict[object, Decimal] = defaultdict(Decimal)
        for row in tables["invoices"].rows:
            invoice_id, order_id, due_date, amount_incl = row[0], row[2], row[4], row[7]
            if due_date < REFERENCE_DATE:  # type: ignore[operator]
                outstanding = amount_incl - credited[invoice_id] - paid[invoice_id]  # type: ignore[operator]
                if outstanding > 0:
                    totals[self.orders[order_id][1]] += outstanding
        return dict(totals)


def top(values: dict[object, float] | dict[object, int], *, reverse: bool = True) -> object:
    return sorted(values, key=lambda k: values[k], reverse=reverse)[0]


Q2_2026 = (date(2026, 4, 1), date(2026, 6, 30))
Q3_2026 = (date(2026, 7, 1), date(2026, 9, 30))
YTD_2025 = (date(2025, 1, 1), date(2025, 9, 30))
YTD_2026 = (date(2026, 1, 1), date(2026, 9, 30))
