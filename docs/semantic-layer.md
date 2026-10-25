# Semantic layer

The LLM must not decide what "revenue" or "an active customer" means. Those definitions
are written once, in SQL views (schema `analytics`), documented column by column in
[`backend/src/eaa/semantic/model.toml`](../backend/src/eaa/semantic/model.toml), and
tested against values computed by hand.

## How it fits together

```text
sales.*  (raw tables, owner only)
   │  migrations/versions/0003_analytics_views.py
   ▼
analytics.*  (10 views: the definitions are in their SQL)  ◄── eaa_reader: SELECT only
   │
   ▼
model.toml  (every view, column, type, classification and metric)
   │  tests: the database and the file must agree exactly
   ▼
LLM prompt (milestone 0.4): descriptions and metric definitions, never data rows
```

## Views

| View | Grain | Use it for |
|---|---|---|
| `dataset_info` | one row | The reference date: "today" for every relative period |
| `customers` | customer | Region, country, industry, segment |
| `suppliers` | supplier | Country, lead time |
| `products` | product | Category, supplier, current prices |
| `sales_lines` | line of an invoiced order | **Revenue, margin, volumes, average order value** |
| `orders` | order, any status | Order counts, cancellations, pipeline (not revenue) |
| `invoices` | invoice | Outstanding amounts, overdue invoices, payment delays |
| `customer_activity` | customer | Activity, churn, revenue over the last and previous 12 months |
| `supplier_deliveries` | delivery | Late deliveries |
| `inventory_snapshots` | product and month end | Stock on hand |

## Business definitions

**Net revenue** (`sales_lines.net_revenue`, metric `net_revenue`)
- Scope: lines of **invoiced** orders (shipped or delivered). Pending orders are not
  invoiced yet; cancelled orders never are.
- Discounts: deducted (`discount_amount`, per line).
- Credit notes: deducted from the line they credit, **in the period of the invoice**
  (not on the credit note's own date). A simplification: a credit note in October on a
  September invoice lowers September.
- Reference date: the **invoice date**. Revenue is counted when invoiced, not ordered.
- VAT: excluded.

**Gross margin** = net revenue - cost of goods sold, where the cost is the quantity times
the unit cost **on the order date** (stored on the line: costs change every year).
The margin *rate* is a ratio of sums over the group, never an average of line rates.
Known simplification: returned goods do not reduce the cost of goods sold.

**Active customer**: placed a non-cancelled order in the 90 days up to the reference
date (pending orders count: the customer is buying). **Became inactive**: ordered in the
90 days before those, but not in the last 90.

**Overdue invoice**: due date before the reference date and something still owed.
The amount owed is the amount including VAT, minus credit notes (including VAT), minus
payments received. **Payment delay** of a settled invoice: days between the due date and
the payment that settled it, 0 if on time.

**Late delivery**: delivered after the expected date, or not delivered once the expected
date has passed. The rate is computed among deliveries already due.

## Classification

Every column has one: `public` (identifies nobody), `internal` (business data),
`confidential` (names a business entity: customer company names, to be pseudonymised
before results go to the LLM provider, milestone 0.6), `pii` (personal data).
No view has a `pii` column; `model.toml` lists what is deliberately withheld
(`sales.customer_contacts`, and `sales.dataset_anomalies`, the evaluation's ground truth).

## Tests

- `tests/test_semantic_model.py`: the file loads; no `pii` column; every identifier in a
  metric expression is a column of its view; inconsistent files are rejected.
- `tests/db/test_semantic_views.py`: views and file agree exactly (names and types, both
  ways); **every metric equals a value computed by hand** on a five-order company; net
  revenue on the generated data equals an independent Python computation.
- `tests/db/test_reader_role.py`: what `eaa_reader` can and cannot do.

## Versioning

`model.toml` has a `version`. It is bumped when a definition changes meaning, so that an
evaluation report can say which definitions it measured.
