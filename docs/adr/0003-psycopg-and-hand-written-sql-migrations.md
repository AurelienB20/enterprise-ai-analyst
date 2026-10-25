# ADR 0003: psycopg 3 and hand-written SQL migrations

- Status: accepted
- Date: 2026-10-25

## Context

The backend talks to PostgreSQL for three jobs: migrations, bulk loading of the synthetic
data, and (from milestone 0.3) running validated, generated SQL under a restricted role,
with session settings such as `statement_timeout` and a read-only transaction.

## Decision

- **psycopg 3** as the only driver. It does fast `COPY` for loading, exposes the session
  and transaction controls the executor needs, and SQLAlchemy and Alembic use it too.
- **Alembic with hand-written SQL** in the migrations, not ORM autogeneration. The schema
  is the product: constraints, comments and indexes are written out and reviewed as SQL,
  the language the LLM will also have to read.
- URLs are stored in libpq form (`postgresql://`) and converted for SQLAlchemy in one
  place (`eaa.db.sqlalchemy_url`).
- Database tests run against a disposable `*_test` database (the fixture refuses any
  other name), migrate it down and up, and roll back their writes.

## Consequences

- No ORM models for the `sales` tables: the application never writes to them.
- Whether the API itself uses sync or async database access is decided with milestone
  0.3, when the executor is written.
