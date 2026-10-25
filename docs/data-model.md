# Data model

The fictional company is based in France and sells office and facility products
(furniture, IT hardware, supplies, cleaning, safety...) to businesses across Europe.
**All data is synthetic**, generated from a fixed seed by `eaa.synthetic`.

## Conventions

- Amounts are euros, `numeric(12,2)`, **excluding VAT** unless the column says otherwise
  (`amount_incl_vat`, `payments.amount`).
- VAT: French customers are invoiced at 20 %. Other EU customers fall under the
  reverse-charge rule and non-EU customers (CH, NO, GB) are exports: both at 0 %.
- Statuses are `text` with `CHECK` constraints rather than enum types.
- Data covers **2023-01-01 to 2026-09-30**. The last day is the **reference date**,
  "today" for every analysis (`sales.dataset_metadata.reference_date`): "last month"
  means September 2026 in every run, so answers stay reproducible.

## Tables (schema `sales`)

| Table | Content | Notes |
|---|---|---|
| `dataset_metadata` | One row: generator version, seed, scale, period | |
| `dataset_anomalies` | The injected anomalies (below) | Ground truth for the evaluation; never exposed to generated SQL |
| `categories` | 10 product categories | |
| `suppliers` | Suppliers, country, usual lead time | |
| `products` | SKU, name, category, supplier, **current** list price and unit cost | |
| `customers` | Company name, country, sales region, industry, segment, payment terms | Segment: top 5 % by size are Enterprise, next 25 % Mid-Market |
| `customer_contacts` | First and last name, email, phone, job title | **Personal data on purpose** (synthetic): what the privacy layer must protect |
| `orders` | Customer, date, status | `pending`, `shipped`, `delivered`, `cancelled` |
| `order_items` | Quantity, list price **and unit cost on the order date**, discount | Prices rise every 1 January, so history lives on the line, not on the product |
| `invoices` | One per shipped or delivered order; amounts excl. and incl. VAT; due date | `status` is the payment status on the reference date; *overdue* is derived from `due_date`, not stored |
| `credit_notes` | Partial credits on an invoice: return, pricing error, goodwill | They reduce what the customer owes |
| `payments` | Amounts received (incl. VAT), method | Only payments made by the reference date exist |
| `supplier_deliveries` | Purchase date, expected and actual delivery date | `delivered_date` is NULL when not delivered yet |
| `inventory_snapshots` | Stock on hand per product at each month end | Not reconciled with deliveries and sales (a known simplification) |

Business definitions (revenue, gross margin, active customer, late payment) are not
decided here: they belong to the semantic layer (milestone 0.2).

## Realism

- **Seasonality**: a B2B pattern, quiet in August, busy from September to November.
- **Growth**: about 8 % more orders per year.
- **Customer sizes**: heavy-tailed (log-normal order weights): a few key accounts,
  many small customers. New customers keep arriving over the period.
- **Prices**: 2 to 5 % yearly increases per category; 20 to 50 % of lines discounted
  (3 to 20 %) depending on the segment.
- **Cancellations**: about 4 % of orders, never invoiced.
- **Payments**: 72 % of customers pay around the due date, 22 % are late (5 to 45 days),
  6 % chronically late (30 to 120 days, 4 % of their invoices never paid); 5 % of
  invoices are paid in two instalments.
- **Suppliers**: 5 to 15 % of deliveries late by 1 to 6 days, except one.

## Injected anomalies

They make the evaluation objective: each one is the expected answer to a question.
They are recorded in `sales.dataset_anomalies`, and `tests/test_synthetic_anomalies.py`
checks that each one is the clear answer, for seed 42 at both scales. Other seeds give
the same answers most of the time, but not always: in a test on 21 seeds, 19 passed every
check. Use seed 42.

| Code | What was injected | Question it answers |
|---|---|---|
| A1_CHURNED_KEY_ACCOUNT | The largest customer (order weight x3) orders nothing from 2026-07-01 | Which customers' revenue dropped the most this quarter? Which customers became inactive? |
| A2_CATEGORY_DROP | Printing loses 45 % of its order lines from 2026-07-01 | Which category dropped the most this quarter? |
| A3_LATE_SUPPLIER | One supplier delivers 70 % of the time 5 to 25 days late | Which suppliers are the most often late? |
| A4_NEGATIVE_MARGIN | One Breakroom product costs 115 % of its price | Which products have the lowest margin? |
| A5_REGION_GROWTH | Southern Europe: order volume x1.7 from 2026-01-01 | Which region grows the fastest? |
| A6_UNPAID_CUSTOMER | A large French customer, a good payer until then, pays nothing invoiced from 2026-01-01 | Which customer owes the most overdue money? |
| A7_ONE_OFF_BIG_ORDER | One order of 120 units of the most expensive IT product, 2025-03-14 | Outlier detection; it inflates Q1 2025 |
| A8_RETURNS_SPIKE | Half the May 2026 invoices of one Lighting product are credited as returns | Which product had a returns spike? |

## Scales

| Scale | Customers | Products | Orders | Generation |
|---|---|---|---|---|
| `small` (default, development and tests) | 1,000 | 300 | 20,000 | about 1 s |
| `full` | 10,000 | 2,000 | 100,000 (230,000 lines) | about 8 s |

```
cd backend
uv run alembic upgrade head
uv run python -m eaa.synthetic --scale small --seed 42
uv run python -m eaa.synthetic --dry-run --scale full   # counts only
```

`--replace` empties the sales tables before loading: it is destructive and needs the
owner's approval on the development database.
