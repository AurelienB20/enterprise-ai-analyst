# Enterprise AI Analyst

**Ask questions about your business data. Get trusted insights, secure SQL and interactive visualizations.**

> Status: early development (milestone 0.7: checked explanations). A question becomes validated SQL,
> runs read-only and comes back with its full trace. No interface yet.

**Measured on 53 business questions** (reference SQL, result comparison, 8 injected
anomalies, 7 questions to refuse): every answer right with Claude Opus 5.5, Opus 5.5 at
low effort and Sonnet 5.5; 0 permission violations; median 3.7 to 5.2 s and $0.006 to
$0.015 per question. The evaluation also found a 31 s query, now 1.6 s.
Each answer comes with a written explanation in which **every number is checked** against
the result: 25 of 25 verified on the dev split.
[Method](docs/evaluation.md) and [results](backend/eval/results/README.md).

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
- [Security of generated SQL: layers, attack corpus, residual risks](docs/security.md)
- [Evaluation: method](docs/evaluation.md) and [results](backend/eval/results/README.md)
- [Privacy by design: data flows, pseudonymisation, re-identification risks](docs/privacy.md)
- [Architecture decision records](docs/adr/)

## Run locally

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/) and PostgreSQL 16.

```
cd backend
uv sync
cp .env.example .env        # then set the passwords
# as the PostgreSQL superuser, once: the roles and the eaa / eaa_test databases
psql -v ON_ERROR_STOP=1 -v owner_password=... -f scripts/create_local_databases.sql
psql -v ON_ERROR_STOP=1 -v reader_password=... -v app_password=... -f scripts/create_roles.sql
uv run alembic upgrade head
uv run python -m eaa.synthetic --scale small --seed 42
uv run python -m eaa.execution "SELECT region, COUNT(*) FROM customers GROUP BY 1"   # no LLM
uv run python -m eaa.orchestrator "Quel est le chiffre d'affaires du mois dernier ?" # calls Claude
uv run uvicorn eaa.main:create_app --factory --reload
```

Then open http://127.0.0.1:8000/docs and try `POST /analyses` with
`{"question": "Which category dropped the most this quarter?"}`. The response carries the
SQL that the model proposed, the SQL that actually ran, every rejected attempt, the
assumptions, the rows, timings, tokens and cost.

## Checks

```
cd backend
uv run ruff format --check . && uv run ruff check . && uv run mypy
uv run pytest                        # unit tests, the LLM is simulated
uv run pytest -m "db and not live"   # database tests, against a disposable *_test database
uv run pytest -m live -s             # real Claude calls (about $0.10): only on purpose
uv run python -m eaa.evaluation run --label my-run --split dev   # the evaluation (about $0.35)
```

## License

MIT, see [LICENSE](LICENSE). All data in this project is synthetic.
