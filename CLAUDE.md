# CLAUDE.md

Rules for Claude Code (and any contributor) working in this repository.

## Project

Enterprise AI Analyst: natural-language questions over a synthetic company database,
answered with validated, read-only SQL and verifiable results.
Core principle: **the LLM proposes, the backend verifies, the database enforces permissions.**

- Architecture: `docs/architecture.md`. Decisions: `docs/adr/`.
- Code, docs and commit messages are in English. Conversation with the owner is in French.

## Hard rules

1. **Never destroy data.** No `DROP DATABASE`, `DROP SCHEMA`, `TRUNCATE` on a persistent
   database, no deletion of Docker volumes or database backups, without explicit approval
   from the owner. Ask before any destructive operation, even in development.
   This includes `python -m eaa.synthetic --replace` and `alembic downgrade` on `eaa`.
   Only `eaa_test` is disposable: the `-m db` tests migrate it down and up. Iterate there.
2. **No paid API call without approval.** Tests mock the LLM. Tests that call real
   services carry the `live` marker and are only run when the owner agrees. Say the
   expected cost before asking.
3. **No push, no public repository, no deployment without approval.** Commit only after
   the owner has validated the milestone.
4. **No secrets in Git.** Secrets live in `backend/.env` (ignored). `.env.example` holds
   placeholders only.
5. **Synthetic data only.** No real company or personal data, ever.
6. **The LLM never gets direct database access.** Every generated query goes through the
   validator, then the executor, under the least-privilege reader role.
7. **No dependency without a concrete need.** No LangChain, LangGraph, MCP, Redis, Celery
   or vector database unless an ADR justifies it.

## Local environment (Windows + Debian WSL)

Docker Desktop is too heavy for this machine: develop natively, keep the Dockerfiles for
deployment only. **Do not leave Docker running.**

- Python 3.12 with uv. From `backend/`: `uv sync`, then
  `uv run uvicorn eaa.main:create_app --factory --reload`.
  If a foreign virtualenv is active, `unset VIRTUAL_ENV` first.
- PostgreSQL 16 runs in WSL:
  `wsl -d Debian -u root -- service postgresql start|stop|status`.
- **The WSL cluster was created in SQL_ASCII.** Create every database of this project in
  UTF8: `CREATE DATABASE ... ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C.utf8' LC_CTYPE 'C.utf8'`.
  Roles and databases are created as the `postgres` superuser, by the idempotent
  `backend/scripts/create_local_databases.sql` (usage in its header).
- Local URLs and the generated owner password are in `backend/.env` (ignored by Git).
- Stop every server you started (uvicorn, `next dev`, PostgreSQL if you started it)
  at the end of a session.

## Checks before any commit

From `backend/`:

```
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest            # unit tests; add -m db for database tests, never -m live without approval
```

## Pitfalls on this machine

- In Git Bash heredocs, apostrophes break the command and `\\` collapses to `\`: write
  files with the editor tools, not heredocs.
- Writing files from Python on Windows turns LF into CRLF unless `newline=""` is passed.
- Each milestone: present the plan, implement with tests, report results and limits, then
  wait for validation.
