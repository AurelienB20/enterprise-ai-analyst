# Enterprise AI Analyst

**Ask questions about your business data. Get trusted insights, secure SQL and interactive visualizations.**

> Status: early development (milestone 0.0, project skeleton). Nothing answers questions yet.

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

See [docs/architecture.md](docs/architecture.md) for the target architecture and the roadmap.

## Run locally

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/).

```
cd backend
uv sync
uv run uvicorn eaa.main:create_app --factory --reload
```

Then open http://127.0.0.1:8000/health or http://127.0.0.1:8000/docs.

## Checks

```
cd backend
uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pytest
```

## License

MIT, see [LICENSE](LICENSE). All data in this project is synthetic.
