"""Seeded generator of the synthetic company dataset.

``generate(seed, scale)`` is a pure function: the same seed and scale give the same rows,
byte for byte (see ``Dataset.digest``). It uses one ``random.Random`` and iterates over
lists and insertion-ordered dicts only, never over sets.

Realism comes from a few explicit mechanisms: monthly seasonality and yearly growth,
heavy-tailed customer sizes (a few key accounts), yearly price increases, discounts,
cancellations, payment behaviours, supplier reliability. On top of that, the anomalies
in ``ANOMALIES`` are injected on purpose and recorded in ``sales.dataset_anomalies``, so
the evaluation has known answers. docs/data-model.md describes each one.
"""

import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from itertools import accumulate
from typing import Literal

from eaa.synthetic import catalog

GENERATOR_VERSION = "2"  # 2: credit notes name the product they credit
START_DATE = date(2023, 1, 1)
# "Today" for every analysis: the data stops here, so "last month" never drifts.
REFERENCE_DATE = date(2026, 9, 30)

ScaleName = Literal["small", "full"]


@dataclass(frozen=True)
class Scale:
    customers: int
    products: int
    suppliers: int
    orders: int


SCALES: dict[ScaleName, Scale] = {
    "small": Scale(customers=1_000, products=300, suppliers=12, orders=20_000),
    "full": Scale(customers=10_000, products=2_000, suppliers=26, orders=100_000),
}

# Anomaly parameters, also described in docs/data-model.md.
CHURN_DATE = date(2026, 7, 1)  # A1: the largest customer orders nothing from here on
KEY_ACCOUNT_BOOST = 3.0  # A1: its order weight, relative to the heavy-tailed draw
CATEGORY_DROP = ("Printing", date(2026, 7, 1), 0.45)  # A2: share of its lines lost in Q3 2026
LATE_SUPPLIER_INDEX = 2  # A3: the third supplier is chronically late
REGION_BOOM = ("Southern Europe", date(2026, 1, 1), 1.7)  # A5: order volume x1.7 in 2026
UNPAID_FROM = date(2026, 1, 1)  # A6: one customer stops paying from here on
UNPAID_CUSTOMER_BOOST = 2.0  # A6: its order weight, so its unpaid total stands out
BIG_ORDER_DATE = date(2025, 3, 14)  # A7: one-off order of many units of an expensive product
BIG_ORDER_QUANTITY = 120
RETURNS_MONTH = date(2026, 5, 1)  # A8: half the lines of one lighting product are returned

CENT = Decimal("0.01")
Row = tuple[object, ...]
Segment = Literal["SMB", "Mid-Market", "Enterprise"]
Behaviour = Literal["prompt", "late", "chronic"]
BEHAVIOURS: tuple[Behaviour, ...] = ("prompt", "late", "chronic")
BEHAVIOUR_WEIGHTS = (0.72, 0.22, 0.06)


def money(value: Decimal | float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, ROUND_HALF_UP)


@dataclass
class Table:
    name: str
    columns: tuple[str, ...]
    rows: list[Row] = field(default_factory=list)


@dataclass
class Dataset:
    seed: int
    scale: ScaleName
    # In foreign-key order: loading them in this order never breaks a constraint.
    tables: dict[str, Table]

    def digest(self) -> str:
        """SHA-256 of every row of every table, for reproducibility checks."""
        sha = hashlib.sha256()
        for table in self.tables.values():
            sha.update(table.name.encode())
            for row in table.rows:
                sha.update(repr(row).encode())
        return sha.hexdigest()


# eq=False: compared by identity, which is what "the same product" means here.
@dataclass(eq=False)
class _Product:
    id: int
    category: catalog.CategorySpec
    supplier_id: int
    base_price: Decimal  # 2023 list price
    cost_ratio: Decimal
    popularity: float

    def price_in(self, year: int) -> Decimal:
        factor = (1 + self.category.yearly_increase) ** (year - START_DATE.year)
        return money(self.base_price * Decimal(str(factor)))

    def cost_in(self, year: int) -> Decimal:
        return money(self.price_in(year) * self.cost_ratio)


@dataclass(eq=False)
class _Customer:
    id: int
    country: str
    region: str
    segment: Segment
    weight: float
    payment_terms: int
    behaviour: Behaviour
    payment_method: str
    created_at: date


@dataclass
class _Supplier:
    id: int
    lead_time: int
    late_probability: float
    late_days: tuple[int, int]


def month_starts(start: date, end: date) -> list[date]:
    months, current = [], start.replace(day=1)
    while current <= end:
        months.append(current)
        current = (current + timedelta(days=32)).replace(day=1)
    return months


def month_end(month: date) -> date:
    return (month + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def _random_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _largest_remainder(total: int, weights: Sequence[float]) -> list[int]:
    """Split ``total`` into integers proportional to ``weights``, summing exactly to it."""
    weight_sum = sum(weights)
    raw = [total * w / weight_sum for w in weights]
    counts = [int(r) for r in raw]
    by_remainder = sorted(range(len(raw)), key=lambda i: (counts[i] - raw[i], i))
    for i in by_remainder[: total - sum(counts)]:
        counts[i] += 1
    return counts


# The sales tables and their columns, in foreign-key order.
TABLE_COLUMNS: dict[str, tuple[str, ...]] = dict(
    (
        (
            "dataset_metadata",
            ("id", "generator_version", "seed", "scale", "start_date", "reference_date"),
        ),
        ("dataset_anomalies", ("code", "description", "entity_type", "entity_id")),
        ("categories", ("id", "category_name")),
        ("suppliers", ("id", "supplier_name", "country", "lead_time_days")),
        (
            "products",
            (
                "id",
                "sku",
                "product_name",
                "category_id",
                "supplier_id",
                "unit_price",
                "cost_price",
                "created_at",
            ),
        ),
        (
            "customers",
            (
                "id",
                "customer_name",
                "country",
                "region",
                "industry",
                "segment",
                "payment_terms_days",
                "created_at",
            ),
        ),
        (
            "customer_contacts",
            ("id", "customer_id", "first_name", "last_name", "email", "phone", "job_title"),
        ),
        ("orders", ("id", "customer_id", "order_date", "status")),
        (
            "order_items",
            (
                "id",
                "order_id",
                "product_id",
                "quantity",
                "unit_price",
                "unit_cost",
                "discount_amount",
            ),
        ),
        (
            "invoices",
            (
                "id",
                "invoice_number",
                "order_id",
                "invoice_date",
                "due_date",
                "amount_excl_vat",
                "vat_rate",
                "amount_incl_vat",
                "status",
            ),
        ),
        (
            "credit_notes",
            (
                "id",
                "invoice_id",
                "product_id",
                "credit_note_date",
                "amount_excl_vat",
                "reason",
            ),
        ),
        ("payments", ("id", "invoice_id", "payment_date", "amount", "payment_method")),
        (
            "supplier_deliveries",
            (
                "id",
                "supplier_id",
                "product_id",
                "quantity",
                "order_date",
                "expected_date",
                "delivered_date",
            ),
        ),
        ("inventory_snapshots", ("snapshot_date", "product_id", "quantity_on_hand")),
    )
)


class _Generator:
    def __init__(self, seed: int, scale: ScaleName) -> None:
        self.rng = random.Random(seed)
        self.seed = seed
        self.scale_name = scale
        self.scale = SCALES[scale]
        self.tables = {name: Table(name, columns) for name, columns in TABLE_COLUMNS.items()}
        self.months = month_starts(START_DATE, REFERENCE_DATE)
        self.products: list[_Product] = []
        self.customers: list[_Customer] = []
        self.suppliers: list[_Supplier] = []
        # Orders as (id, customer, date, status) and their lines as (product, net amount
        # excluding VAT): typed copies of the rows, for the tables that derive from them.
        self.orders: list[tuple[int, _Customer, date, str]] = []
        self.order_lines: dict[int, list[tuple[_Product, Decimal]]] = {}

    def _add(self, table: str, row: Row) -> None:
        self.tables[table].rows.append(row)

    def _anomaly(self, code: str, description: str, entity_type: str, entity_id: int) -> None:
        self._add("dataset_anomalies", (code, description, entity_type, entity_id))

    # -- reference data --------------------------------------------------------------

    def categories(self) -> None:
        for index, spec in enumerate(catalog.CATEGORIES, start=1):
            self._add("categories", (index, spec.name))

    def suppliers_table(self) -> None:
        countries = [c for countries in catalog.REGIONS.values() for c in countries]
        for index in range(self.scale.suppliers):
            supplier = _Supplier(
                id=index + 1,
                lead_time=self.rng.randint(7, 21),
                late_probability=self.rng.uniform(0.05, 0.15),
                late_days=(1, 6),
            )
            if index == LATE_SUPPLIER_INDEX:
                supplier.late_probability, supplier.late_days = 0.70, (5, 25)
            self.suppliers.append(supplier)
            name = catalog.SUPPLIER_NAMES[index]
            self._add(
                "suppliers", (supplier.id, name, self.rng.choice(countries), supplier.lead_time)
            )
        late = self.suppliers[LATE_SUPPLIER_INDEX]
        self._anomaly(
            "A3_LATE_SUPPLIER",
            "About 70 % of this supplier's deliveries arrive 5 to 25 days late.",
            "supplier",
            late.id,
        )

    def products_table(self) -> None:
        per_category = _largest_remainder(self.scale.products, [1.0] * len(catalog.CATEGORIES))
        product_id = 0
        for category_id, (spec, count) in enumerate(
            zip(catalog.CATEGORIES, per_category, strict=True), start=1
        ):
            for n in range(count):
                product_id += 1
                low, high = spec.price_range
                product = _Product(
                    id=product_id,
                    category=spec,
                    supplier_id=self.rng.randint(1, self.scale.suppliers),
                    base_price=money(self.rng.uniform(low, high)),
                    cost_ratio=Decimal(str(round(1 - self.rng.uniform(*spec.margin_range), 4))),
                    popularity=self.rng.lognormvariate(0, 1.0),
                )
                self.products.append(product)
                name = (
                    f"{self.rng.choice(catalog.BRANDS)} {spec.nouns[n % len(spec.nouns)]} "
                    f"{chr(65 + n % 26)}-{100 + n}"
                )
                current_year = REFERENCE_DATE.year
                self._add(
                    "products",
                    (
                        product.id,
                        f"{spec.code}-{n + 1:05d}",
                        name,
                        category_id,
                        product.supplier_id,
                        product.price_in(current_year),
                        product.cost_in(current_year),
                        _random_date(self.rng, date(2021, 1, 1), date(2022, 12, 31)),
                    ),
                )
        # A4: a pricing error, the product costs more than it sells for.
        mispriced = next(p for p in self.products if p.category.name == "Breakroom")
        mispriced.cost_ratio = Decimal("1.15")
        row = list(self.tables["products"].rows[mispriced.id - 1])
        row[6] = mispriced.cost_in(REFERENCE_DATE.year)
        self.tables["products"].rows[mispriced.id - 1] = tuple(row)
        self._anomaly(
            "A4_NEGATIVE_MARGIN",
            "Pricing error: unit cost is 115 % of the list price, so every sale loses money.",
            "product",
            mispriced.id,
        )

    def customers_table(self) -> None:
        regions = list(catalog.REGION_WEIGHTS)
        region_weights = list(catalog.REGION_WEIGHTS.values())
        weights = [self.rng.lognormvariate(0, 1.0) for _ in range(self.scale.customers)]
        ranked = sorted(range(len(weights)), key=lambda i: -weights[i])
        segment_of: dict[int, Segment] = {}
        for rank, index in enumerate(ranked):
            share = rank / len(ranked)
            segment_of[index] = (
                "Enterprise" if share < 0.05 else "Mid-Market" if share < 0.30 else "SMB"
            )
        terms: dict[Segment, int] = {"SMB": 30, "Mid-Market": 45, "Enterprise": 60}
        names: set[str] = set()
        contact_id = 0
        for index, weight in enumerate(weights):
            region = self.rng.choices(regions, region_weights)[0]
            country = self.rng.choice(catalog.REGIONS[region])
            industry = self.rng.choice(catalog.INDUSTRIES)
            behaviour = self.rng.choices(BEHAVIOURS, BEHAVIOUR_WEIGHTS)[0]
            created_at = (
                _random_date(self.rng, date(2018, 1, 1), date(2022, 12, 31))
                if self.rng.random() < 0.6
                else _random_date(self.rng, START_DATE, date(2026, 8, 31))
            )
            customer = _Customer(
                id=index + 1,
                country=country,
                region=region,
                segment=segment_of[index],
                weight=weight,
                payment_terms=terms[segment_of[index]],
                behaviour=behaviour,
                payment_method=self.rng.choices(
                    catalog.PAYMENT_METHODS, catalog.PAYMENT_METHOD_WEIGHTS
                )[0],
                created_at=created_at,
            )
            self.customers.append(customer)
            name = self._company_name(industry, country, names)
            self._add(
                "customers",
                (
                    customer.id,
                    name,
                    country,
                    region,
                    industry,
                    customer.segment,
                    customer.payment_terms,
                    created_at,
                ),
            )
            domain = "".join(ch for ch in name.lower() if ch.isalnum())[:24]
            for _ in range(self.rng.randint(1, 3)):
                contact_id += 1
                first = self.rng.choice(catalog.FIRST_NAMES)
                last = self.rng.choice(catalog.LAST_NAMES)
                self._add(
                    "customer_contacts",
                    (
                        contact_id,
                        customer.id,
                        first,
                        last,
                        f"{first.lower()}.{last.lower()}@{domain}.example",
                        f"+1-555-01{self.rng.randint(0, 99):02d}",
                        self.rng.choice(catalog.JOB_TITLES),
                    ),
                )

        # A1: the key account that churns, made large enough to be the obvious answer.
        self.key_account = max(
            (c for c in self.customers if c.created_at < START_DATE), key=lambda c: c.weight
        )
        self.key_account.weight *= KEY_ACCOUNT_BOOST
        # A6: a good payer with many invoices, so that it stands out once it stops paying.
        self.unpaid_customer = max(
            (
                c
                for c in self.customers
                if c is not self.key_account
                and c.country == catalog.HOME_COUNTRY
                and c.created_at < START_DATE
                and c.behaviour == "prompt"
            ),
            key=lambda c: c.weight,
        )
        self.unpaid_customer.weight *= UNPAID_CUSTOMER_BOOST

    def _company_name(self, industry: str, country: str, taken: set[str]) -> str:
        base = (
            f"{self.rng.choice(catalog.COMPANY_PREFIXES)} {self.rng.choice(catalog.COMPANY_ROOTS)} "
            f"{self.rng.choice(catalog.COMPANY_SECTOR_WORDS[industry])} "
            f"{catalog.LEGAL_FORMS[country]}"
        )
        name, n = base, 1
        while name in taken:
            n += 1
            name = f"{base} {n}"
        taken.add(name)
        return name

    # -- orders and what follows them --------------------------------------------

    def _month_weight(self, month: date) -> float:
        months_elapsed = (month.year - START_DATE.year) * 12 + month.month - 1
        growth: float = (1 + catalog.YEARLY_GROWTH) ** (months_elapsed / 12)
        return catalog.SEASONALITY[month.month] * growth

    def _customer_weight(self, customer: _Customer, month: date) -> float:
        region, since, factor = REGION_BOOM
        if customer.region == region and month >= since:
            return customer.weight * factor
        return customer.weight

    def orders_table(self) -> None:
        churned = self.key_account
        self._anomaly(
            "A1_CHURNED_KEY_ACCOUNT",
            f"The largest customer places no order from {CHURN_DATE.isoformat()} on.",
            "customer",
            churned.id,
        )
        region, since, factor = REGION_BOOM
        self._anomaly(
            "A5_REGION_GROWTH",
            f"{region}: order volume x{factor} from {since.isoformat()}, the fastest growth.",
            "region",
            0,
        )
        category, drop_from, drop_share = CATEGORY_DROP
        category_id = next(i for i, c in enumerate(catalog.CATEGORIES, 1) if c.name == category)
        self._anomaly(
            "A2_CATEGORY_DROP",
            f"{category}: {int(drop_share * 100)} % of its order lines lost from "
            f"{drop_from.isoformat()} (Q3 2026).",
            "category",
            category_id,
        )

        product_cumulative = list(accumulate(p.popularity for p in self.products))
        counts = _largest_remainder(self.scale.orders, [self._month_weight(m) for m in self.months])
        big_order_customer = next(
            c
            for c in self.customers
            if c.segment == "Mid-Market"
            and c.region == "Central Europe"
            and c.created_at < START_DATE
        )
        order_id = 0
        item_id = 0
        for month, count in zip(self.months, counts, strict=True):
            eligible = [
                c
                for c in self.customers
                if c.created_at <= month and not (c is churned and month >= CHURN_DATE)
            ]
            cumulative = list(accumulate(self._customer_weight(c, month) for c in eligible))
            last_day = min(month_end(month), REFERENCE_DATE)
            orders = [
                (_random_date(self.rng, month, last_day), customer)
                for customer in self.rng.choices(eligible, cum_weights=cumulative, k=count)
            ]
            if month == BIG_ORDER_DATE.replace(day=1):
                orders.append((BIG_ORDER_DATE, big_order_customer))
            orders.sort(key=lambda o: (o[0], o[1].id))
            for order_date, customer in orders:
                order_id += 1
                is_big_order = order_date == BIG_ORDER_DATE and customer is big_order_customer
                status = self._status(order_date)
                self.orders.append((order_id, customer, order_date, status))
                self._add("orders", (order_id, customer.id, order_date, status))
                lines = (
                    self._big_order_lines()
                    if is_big_order
                    else self._order_lines(order_date, customer, product_cumulative, drop_from)
                )
                self.order_lines[order_id] = []
                for product, quantity, discount in lines:
                    item_id += 1
                    price = product.price_in(order_date.year)
                    self._add(
                        "order_items",
                        (
                            item_id,
                            order_id,
                            product.id,
                            quantity,
                            price,
                            product.cost_in(order_date.year),
                            discount,
                        ),
                    )
                    self.order_lines[order_id].append((product, price * quantity - discount))
                if is_big_order:
                    self._anomaly(
                        "A7_ONE_OFF_BIG_ORDER",
                        f"One-off order of {BIG_ORDER_QUANTITY} units of the most expensive "
                        f"IT Hardware product on {BIG_ORDER_DATE.isoformat()}.",
                        "order",
                        order_id,
                    )

    def _status(self, order_date: date) -> str:
        age = (REFERENCE_DATE - order_date).days
        if self.rng.random() < 0.04:
            return "cancelled"
        if age < 7 and self.rng.random() < 0.6:
            return "pending"
        if age < 14:
            return "shipped"
        return "delivered"

    def _order_lines(
        self,
        order_date: date,
        customer: _Customer,
        product_cumulative: list[float],
        drop_from: date,
    ) -> list[tuple[_Product, int, Decimal]]:
        category, _, drop_share = CATEGORY_DROP
        n_lines = min(8, 1 + int(self.rng.expovariate(1 / 1.8)))
        caps: dict[Segment, int] = {"SMB": 8, "Mid-Market": 20, "Enterprise": 50}
        discount_probability = {"SMB": 0.20, "Mid-Market": 0.35, "Enterprise": 0.50}
        chosen: list[_Product] = []
        while len(chosen) < n_lines:
            product = self.rng.choices(self.products, cum_weights=product_cumulative)[0]
            if product in chosen:
                continue
            if (
                product.category.name == category
                and order_date >= drop_from
                and self.rng.random() < drop_share
            ):
                continue
            chosen.append(product)
        lines = []
        for product in chosen:
            high = max(1.0, caps[customer.segment] * product.category.quantity_factor)
            quantity = max(1, round(self.rng.triangular(1, high, 1)))
            discount = Decimal(0)
            if self.rng.random() < discount_probability[customer.segment]:
                top = 0.20 if customer.segment == "Enterprise" else 0.15
                gross = product.price_in(order_date.year) * quantity
                discount = money(gross * Decimal(str(round(self.rng.uniform(0.03, top), 4))))
            lines.append((product, quantity, discount))
        return lines

    def _big_order_lines(self) -> list[tuple[_Product, int, Decimal]]:
        product = max(
            (p for p in self.products if p.category.name == "IT Hardware"),
            key=lambda p: p.base_price,
        )
        gross = product.price_in(BIG_ORDER_DATE.year) * BIG_ORDER_QUANTITY
        return [(product, BIG_ORDER_QUANTITY, money(gross * Decimal("0.10")))]

    def invoices_and_payments(self) -> None:
        unpaid_customer = self.unpaid_customer
        self._anomaly(
            "A6_UNPAID_CUSTOMER",
            f"This customer pays none of its invoices issued from {UNPAID_FROM.isoformat()} on.",
            "customer",
            unpaid_customer.id,
        )
        returned = max(
            (p for p in self.products if p.category.name == "Lighting"),
            key=lambda p: p.popularity,
        )
        self._anomaly(
            "A8_RETURNS_SPIKE",
            f"Half of the invoiced lines of this product in {RETURNS_MONTH:%Y-%m} are "
            "returned and credited.",
            "product",
            returned.id,
        )
        invoice_id = credit_id = payment_id = 0
        for order_id, customer, order_date, status in self.orders:
            if status not in ("shipped", "delivered"):
                continue
            invoice_id += 1
            invoice_date = min(order_date + timedelta(days=self.rng.randint(0, 3)), REFERENCE_DATE)
            due_date = invoice_date + timedelta(days=customer.payment_terms)
            lines = self.order_lines[order_id]
            amount = sum((net for _, net in lines), Decimal(0))
            vat_rate = (
                catalog.HOME_VAT_RATE
                if customer.country == catalog.HOME_COUNTRY
                else Decimal("0.000")
            )
            amount_incl = money(amount * (1 + vat_rate))

            # A credit note credits one line of the invoice: (date, product, amount, reason).
            credits: list[tuple[date, _Product, Decimal, str]] = []
            if returned in (p for p, _ in lines) and invoice_date.replace(day=1) == RETURNS_MONTH:
                if self.rng.random() < 0.5:
                    net = next(n for p, n in lines if p is returned)
                    credit_date = invoice_date + timedelta(days=self.rng.randint(5, 20))
                    credits.append((credit_date, returned, net, "return"))
            elif self.rng.random() < 0.02 and amount > 0:
                product, net = self.rng.choice(lines)
                reason = self.rng.choice(["return", "pricing_error", "goodwill"])
                share = Decimal(str(round(self.rng.uniform(0.05, 0.5), 4)))
                credit_date = invoice_date + timedelta(days=self.rng.randint(5, 40))
                credits.append((credit_date, product, money(net * share), reason))
            credits = [c for c in credits if c[0] <= REFERENCE_DATE and c[2] > 0]
            credited_incl = sum((money(c[2] * (1 + vat_rate)) for c in credits), Decimal(0))
            owed = amount_incl - credited_incl

            paid = Decimal(0)
            if not (customer is unpaid_customer and invoice_date >= UNPAID_FROM):
                for payment_date, payment_amount in self._payments(customer, due_date, owed):
                    payment_id += 1
                    paid += payment_amount
                    self._add(
                        "payments",
                        (
                            payment_id,
                            invoice_id,
                            payment_date,
                            payment_amount,
                            customer.payment_method,
                        ),
                    )
            status_on_reference = (
                "paid" if paid >= owed else "partially_paid" if paid > 0 else "open"
            )
            self._add(
                "invoices",
                (
                    invoice_id,
                    f"INV-{invoice_date.year}-{invoice_id:06d}",
                    order_id,
                    invoice_date,
                    due_date,
                    amount,
                    vat_rate,
                    amount_incl,
                    status_on_reference,
                ),
            )
            for credit_date, product, credit_amount, reason in credits:
                credit_id += 1
                self._add(
                    "credit_notes",
                    (credit_id, invoice_id, product.id, credit_date, credit_amount, reason),
                )

    def _payments(
        self, customer: _Customer, due_date: date, owed: Decimal
    ) -> list[tuple[date, Decimal]]:
        """Payments received by the reference date; later ones simply do not exist yet."""
        if owed <= 0:
            return []
        if customer.behaviour == "prompt":
            delay = self.rng.randint(-10, 5)
        elif customer.behaviour == "late":
            delay = self.rng.randint(5, 45)
        else:
            if self.rng.random() < 0.04:
                return []
            delay = self.rng.randint(30, 120)
        first_date = due_date + timedelta(days=delay)
        if self.rng.random() < 0.05:
            first = money(owed * Decimal("0.6"))
            payments = [(first_date, first), (first_date + timedelta(days=30), owed - first)]
        else:
            payments = [(first_date, owed)]
        return [(d, amount) for d, amount in payments if d <= REFERENCE_DATE]

    # -- supply side ---------------------------------------------------------------

    def supplier_deliveries(self) -> None:
        delivery_id = 0
        suppliers = {s.id: s for s in self.suppliers}
        for month in self.months:
            last_day = min(month_end(month), REFERENCE_DATE)
            for product in self.products:
                if self.rng.random() >= 0.25:
                    continue
                supplier = suppliers[product.supplier_id]
                delivery_id += 1
                order_date = _random_date(self.rng, month, last_day)
                expected = order_date + timedelta(days=supplier.lead_time)
                if self.rng.random() < supplier.late_probability:
                    delay = self.rng.randint(*supplier.late_days)
                else:
                    delay = self.rng.randint(-2, 0)
                delivered: date | None = max(order_date, expected + timedelta(days=delay))
                if delivered is not None and delivered > REFERENCE_DATE:
                    delivered = None
                quantity = max(
                    1, round(self.rng.uniform(20, 300) * product.category.quantity_factor)
                )
                self._add(
                    "supplier_deliveries",
                    (
                        delivery_id,
                        supplier.id,
                        product.id,
                        quantity,
                        order_date,
                        expected,
                        delivered,
                    ),
                )

    def inventory_snapshots(self) -> None:
        """Month-end stock levels. Not reconciled with deliveries and sales (documented)."""
        for month in self.months:
            snapshot_date = min(month_end(month), REFERENCE_DATE)
            for product in self.products:
                on_hand = (
                    0
                    if self.rng.random() < 0.03
                    else round(50 * product.popularity * self.rng.uniform(0.5, 3.0))
                )
                self._add("inventory_snapshots", (snapshot_date, product.id, on_hand))

    def run(self) -> Dataset:
        self._add(
            "dataset_metadata",
            (1, GENERATOR_VERSION, self.seed, self.scale_name, START_DATE, REFERENCE_DATE),
        )
        self.categories()
        self.suppliers_table()
        self.products_table()
        self.customers_table()
        self.orders_table()
        self.invoices_and_payments()
        self.supplier_deliveries()
        self.inventory_snapshots()
        # Anomalies sorted by code, whatever the order they were found in.
        self.tables["dataset_anomalies"].rows.sort(key=lambda row: str(row[0]))
        return Dataset(seed=self.seed, scale=self.scale_name, tables=self.tables)


def generate(seed: int = 42, scale: ScaleName = "small") -> Dataset:
    return _Generator(seed, scale).run()
