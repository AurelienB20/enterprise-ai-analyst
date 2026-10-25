# ADR 0006: An allowlist validator that runs regenerated SQL

- Status: accepted
- Date: 2026-10-25

## Context

The database role is the security boundary (ADR 0005), but it does not stop everything
(catalog reads, `pg_sleep`, `set_config`), and its errors are poor feedback for an LLM
that should correct its query. A validator in front is needed. Options:

1. **String checks** ("starts with SELECT", a regex for `DROP`): bypassed by CTEs,
   comments, quoting, stacked statements. Rejected.
2. **A denylist on a parse tree**: block the dangerous functions and statements we know
   of. Every new PostgreSQL function or extension is allowed by default. Rejected.
3. **An allowlist on a parse tree**: one read statement, analytics views only, a fixed set
   of analytical functions, every column known. Anything not listed is refused.

And separately: execute the original text, or SQL regenerated from the validated tree?

## Decision

- **Option 3, with SQLGlot** (PostgreSQL dialect): mature, pure Python, no database round
  trip, and it exposes the full tree, including CTEs and subqueries, and a column
  qualifier that checks columns against a schema built from the semantic model.
- **Execute the regenerated SQL**, comments dropped. The validated tree is the contract:
  if SQLGlot misread some unusual input, PostgreSQL still receives what was checked.
  The cost, a regeneration bug changing a query's meaning, is covered by tests that run
  every legitimate query both ways and compare results.
- **The executor** opens a connection per query, in a read-only transaction always rolled
  back, sets its limits with `SET LOCAL`, and reads rows through a server-side cursor
  capped at `max_rows + 1`. It is synchronous: one short query per request, run in a
  worker thread. A connection pool can come later if latency requires it.

## Consequences

- Legitimate SQL that uses an unlisted function is refused: the list grows when the
  evaluation shows a real need, through a reviewed change, never automatically.
- SQLGlot's internal function names (`TIMESTAMP_TRUNC` for `date_trunc`) leak into the
  allowlist; a library upgrade must re-run the corpus.
- Rejections carry a reason code and a message that is safe to show to the user and to
  send back to the LLM for one retry (milestone 0.4).
