# ADR 0005: The database role is the security boundary

- Status: accepted
- Date: 2026-10-25

## Context

Generated SQL is untrusted input: a prompt injection, a confused model or a malicious user
can produce `DELETE`, a read of a table holding personal data, or a call to a function
that reads server files. A SQL parser can catch most of it, but parsers have gaps (dialect
quirks, functions nobody listed, constructs added in a new PostgreSQL version), and one
gap is enough.

## Decision

Generated SQL runs as `eaa_reader`, a role that PostgreSQL itself restricts:

- `CONNECT` on the database and `SELECT` on the `analytics` views, **nothing else**: no
  right on the raw `sales` tables (personal data included), no `CREATE` anywhere, no
  `TEMP`. `PUBLIC` loses its default rights on the database and the `public` schema.
- Not superuser, no `CREATEDB`, `CREATEROLE`, `REPLICATION`, `BYPASSRLS`; at most 10
  connections. Server files and programs (`pg_read_file`, `COPY ... PROGRAM`) are out of
  reach because the role has none of the `pg_*` server roles.
- Session defaults: read-only transactions, `statement_timeout` 10 s, `lock_timeout`,
  `idle_in_transaction_session_timeout`, `work_mem`, `temp_file_limit`, and
  `search_path = analytics`.

The SQL validator (milestone 0.3) comes in front, to reject early and explain why. It is
not the boundary.

Roles belong to the cluster, so `scripts/create_reader_role.sql` creates the role (as
superuser); the Alembic migration grants it rights in the database.

## Consequences

- Each layer is tested on its own: `tests/db/test_reader_role.py` sends writes, DDL and
  server-access calls straight to the database, in read-write transactions, and expects a
  privilege error every time.
- Known gaps, for the next milestones:
  - The session defaults are only defaults: the role can `SET statement_timeout = 0` or
    call `set_config`. The executor sets them again inside each transaction
    and the validator rejects `SET` and `set_config` (0.3).
  - Catalogs (`pg_catalog`, `information_schema`) stay readable, as in any PostgreSQL:
    they reveal table and column names, not data. The validator rejects them.
  - `pg_sleep` and heavy queries can still burn CPU until the timeout.
