# Enterprise AI Analyst

**Ask questions about your business data. Get trusted insights, secure SQL and interactive visualizations.**

> Status: early development (milestone 0.2: semantic layer and read-only role). Nothing
> answers questions yet.

Enterprise AI Analyst turns a business question such as *"Which 10 customers' revenue dropped
the most this quarter?"* into a SQL query, checks it, runs it read-only on a synthetic
company database and returns a result you can verify: the tables, filters, calculations
and the exact SQL that ran.

It is not a raw Text-to-SQL chatbot. Three ideas drive the design:

- **The LLM proposes, the backend verifies, the database enforces permissions.** Generated
  SQL is parsed and validated, then runs under a PostgreSQL role that can only read
  curated views.
- **Business definitions are code, not prompts.** Revenue, gross margin, active customer
  and late payment are defined once, versioned and tested in a semantic layer.
- **Privacy by design.** Personal data is classified by column and never sent to the LLM
  provider; aggregation happens in PostgreSQL before anything leaves the database.

## Documentation

- [Architecture and roadmap](docs/architecture.md)
- [Data model and injected anomalies](docs/data-model.md)
- [Semantic layer: business definitions](docs/semantic-layer.md)
- [Architecture decision records](docs/adr/)

## Run locally

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/) and PostgreSQL 16.

```
cd backend
uv sync
cp .env.example .env        # then set the passwords
# as the PostgreSQL superuser, once: the roles and the eaa / eaa_test databases
psql -v ON_ERROR_STOP=1 -v owner_password=... -f scripts/create_local_databases.sql
psql -v ON_ERROR_STOP=1 -v reader_password=... -f scripts/create_reader_role.sql
uv run alembic upgrade head
uv run python -m eaa.synthetic --scale small --seed 42
uv run uvicorn eaa.main:create_app --factory --reload
```

Then open http://127.0.0.1:8000/health or http://127.0.0.1:8000/docs.

## Checks

```
cd backend
uv run ruff format --check . && uv run ruff check . && uv run mypy
uv run pytest            # unit tests
uv run pytest -m db      # database tests, against TEST_DATABASE_URL (a disposable *_test database)
```

## License

MIT, see [LICENSE](LICENSE). All data in this project is synthetic.
