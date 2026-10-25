# Architecture

Target architecture of Enterprise AI Analyst. Parts marked with a milestone do not exist
yet; this document is updated as each one lands.

## Principle

**The LLM proposes, the backend verifies, the database enforces permissions.**

Probabilistic steps (the LLM) and deterministic steps (validation, authorization,
execution, privacy controls, calculations) are separate modules. A deterministic step
never trusts the output of a probabilistic one.

## Pipeline

```text
Question
  -> Authorization                    who asks, what they may see            (0.9)
  -> Context selection                the whole semantic model, cached        (0.4)
                                      deterministic; no data rows
  -> LLM: submit_query / cannot_answer strict tool calls (ADR 0007)          (0.4)
  -> SQL validator (SQLGlot)          one SELECT, allowlisted views/functions (0.3)
  -> Read-only executor               READ ONLY transaction, timeouts, limit  (0.3)
       under the eaa_reader role      SELECT on analytics views only
  -> Privacy controls                 pseudonymisation, minimum group size    (0.6)
  -> Deterministic calculations       totals, variations, shares              (0.7)
  -> LLM: explanation                 from computed figures only              (0.7)
  -> Number check                     every figure must match a computed one  (0.7)
  -> Answer + Analysis Trace           audit log without personal data         (0.4+)
```

At most three proposals: a validator rejection or a database error goes back to the LLM
as an error tool result, and it corrects its query. That loop does not need an agent
framework (ADR 0007).

## Defense in depth for generated SQL

Each layer is tested separately; [security.md](security.md) has the attack corpus, which
layer stops what, and the residual risks.

1. **Validator** (milestone 0.3). Parses with SQLGlot, walks the whole tree (CTEs,
   subqueries, `LATERAL`, set operations) and accepts only a single `SELECT`/`WITH`
   statement over allowlisted views, calling allowlisted functions. An allowlist, not a
   denylist: a denylist of dangerous functions is never complete.
   It fails early with a clear message, but it is **not** the security boundary.
2. **PostgreSQL role `eaa_reader`** (milestone 0.2, ADR 0005). `SELECT` on the `analytics` schema
   only; no access to raw tables, personal-data columns or the `app` schema. This is the
   boundary: a query that slips past the validator is still refused by the database.
3. **Executor** (milestone 0.3). Read-only transaction with `SET LOCAL statement_timeout`,
   a fixed `search_path`, bounded `work_mem`, and a row limit enforced by fetching at
   most `limit + 1` rows.

## Database layout (milestone 0.1-0.2)

| Schema | Content | Who reads it |
|---|---|---|
| `sales` | Raw synthetic tables: customers, customer_contacts (personal data on purpose), products, categories, orders, order_items, invoices, credit_notes, payments, suppliers, supplier_deliveries, inventory_snapshots | Migrations and the data generator only |
| `analytics` | Semantic views: metric definitions encoded in SQL, no personal-data columns | `eaa_reader` (generated SQL) |
| `app` | Analyses, traces, audit log, usage | The API role, never `eaa_reader` |

All amounts are `numeric(12,2)`, in euros, excluding VAT. The dataset stops at a fixed
reference date, given to the LLM, so that "last month" means the same thing in every run.

## Semantic layer (milestone 0.2)

The business definitions (revenue, gross margin, active customer, late payment) are
encoded in the SQL of the `analytics` views and documented, column by column, in
`backend/src/eaa/semantic/model.toml`; tests check that both agree and compute every
metric by hand. The LLM chooses columns that are already defined; it cannot redefine
revenue. Each column is classified (`public`, `internal`, `confidential`, `pii`): no view
has a `pii` column. See [semantic-layer.md](semantic-layer.md) and ADR 0004.

## What is sent to the LLM provider

| Call | Sent | Never sent |
|---|---|---|
| SQL generation | Question, view and column descriptions, metric definitions, reference date | Data rows, personal data |
| Explanation (0.7) | Aggregated results after privacy controls, computed figures | Columns classified `pii`, mapping tables |

The full table, with what is masked or pseudonymised, is in [privacy.md](privacy.md);
tests assert it. Logs hold IDs, counts and durations, never query results or personal
data.

## Code layout

```text
backend/src/eaa/
  config.py         settings from the environment
  main.py           FastAPI application factory
  api/              routes, middleware, HTTP schemas
  observability/    logging, correlation IDs, usage and cost (later)
  semantic/         metric definitions, column classification          (0.2)
  sql_security/     SQLGlot validator                                  (0.3)
  execution/        read-only executor                                 (0.3)
  llm/              Anthropic client, SQL generation by tool calling   (0.4)
  privacy/          minimisation, pseudonymisation, aggregate controls (0.6)
  analysis/         deterministic calculations, checked explanations   (0.7)
```

## Roadmap

| Milestone | Content | Acceptance |
|---|---|---|
| 0.0 | Skeleton, configuration, logging, CI | Lint, types and tests pass; `/health` answers |
| 0.1 | Schema, Alembic migrations, seeded synthetic data, documented anomalies | Same seed, same data; consistency tests |
| 0.2 | Semantic layer, `analytics` views, column classification, PostgreSQL roles | Each metric tested against a hand-computed value |
| 0.3 | SQL validator, read-only executor, adversarial tests without LLM | Each attack blocked by at least two layers |
| 0.4 | Text-to-SQL with Claude tool calling, `POST /analyses`: first end-to-end MVP | Works end to end; LLM mocked in CI |
| 0.5 | Evaluation: 53 questions with reference SQL, result comparison, dev/test split | A measured baseline (done: docs/evaluation.md) |
| 0.6 | Privacy: question masking, column lineage, pseudonymised provider payload | No company name reaches the payload (done: docs/privacy.md) |
| 0.7 | Analysis: deterministic calculations, explanations, number check | No unchecked figure is shown (done: ADR 0010) |
| 0.8 | Next.js frontend, Recharts, Analysis Trace | Checked in a browser (done) |
| 0.9 | Production readiness: limits and daily budget, Docker stack, HTTPS, backups | Smoke test on the production stack in CI (deploy/, docs/deployment.md) |
