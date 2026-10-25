# ADR 0004: The semantic layer lives in SQL views, documented in TOML

- Status: accepted
- Date: 2026-10-25

## Context

Text-to-SQL systems fail less on SQL syntax than on meaning: counting cancelled orders
as revenue, forgetting credit notes, averaging margin rates, using today's date on data
that stopped weeks ago. If the LLM writes revenue from the raw tables, it re-decides the
definition on every question.

Options considered:

1. **Definitions in the prompt only.** The LLM reads "revenue excludes cancelled orders"
   and must apply it. Nothing enforces it; every query can get it wrong differently.
2. **Definitions in YAML, compiled into SQL.** One source of truth, but a compiler to
   write and test, for ten views.
3. **A metrics DSL**: the LLM picks a metric, dimensions and filters, and the backend
   writes the SQL. The most reliable, the least flexible.
4. **SQL views that encode the definitions, documented in a file, the two checked
   against each other by tests.**

## Decision

Option 4.

- The views (`analytics.*`) contain the definitions: `sales_lines.net_revenue` is already
  net of discounts and credit notes, restricted to invoiced orders, dated by invoice.
  The LLM selects columns that are already right; it cannot redefine revenue.
- `model.toml` documents every view, column, type, classification and metric. TOML because
  the standard library reads it (no dependency) and people write it.
- Tests compare the database and the file exactly, and check every metric against values
  computed by hand.
- Option 3 stays open as a measured experiment once the evaluation exists (milestone 0.5):
  it may be more reliable for the most common questions.

## Consequences

- Definitions are written twice (SQL and prose); the tests catch any drift in names and
  types, not in prose. A reviewer still has to read both when a definition changes.
- Questions the views do not cover cannot be answered; the system should say so rather
  than reach for raw tables, which it cannot read anyway (ADR 0005).
- Views run with their owner's rights: that is what lets `eaa_reader` read them without
  any right on the raw tables.
