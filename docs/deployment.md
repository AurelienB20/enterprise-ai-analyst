# Deployment

The stack in [`deploy/`](../deploy) runs on any Linux server with Docker: PostgreSQL 16,
the migrations, the API, the web interface and Caddy, which serves HTTPS and is the
only published service. The CI builds and starts this exact stack on every push
(job `stack`) and runs [`deploy/smoke-test.sh`](../deploy/smoke-test.sh) against it.

## What runs where

```text
Internet ──443──► Caddy ──► web (Next.js) ──► api (FastAPI) ──► db (PostgreSQL)
                  HTTPS      adds API_KEY      eaa_reader / eaa_app roles
                  HSTS       forwards the      limits per client, per day
                             visitor address
```

- **db**: the volume `db-data`. On first start, `deploy/initdb/01-roles.sh` creates
  `eaa_owner` (owner of the database: migrations, data loading), then `eaa_reader` and
  `eaa_app` with `backend/scripts/create_roles.sql`.
- **migrate**: `alembic upgrade head` as `eaa_owner`, then exits. The API waits for it.
- **seed** (profile, run by hand once): loads the synthetic dataset.
- **api**: never published; reads as `eaa_reader`, writes the audit trail as `eaa_app`.
  Requires `API_KEY` and `DAILY_BUDGET_USD` (it refuses to start in production without).
- **web**: holds `API_KEY` server-side; the browser never sees it.
- **caddy**: obtains and renews the certificate for `DOMAIN`.

## Server

A small VPS is enough for a demo: the API runs one worker, PostgreSQL holds about
100 MB with the small dataset. 2 vCPU and 4 GB of RAM leave room for the image builds;
2 GB works if the images are built elsewhere. Check current prices on the provider's
own site before choosing.

## First deployment

```sh
# On the server, with Docker and the Compose plugin installed, and the domain's DNS
# record pointing to the server:
git clone https://github.com/AurelienB20/enterprise-ai-analyst.git
cd enterprise-ai-analyst/deploy
cp .env.example .env
# Fill in .env: DOMAIN, every password and API_KEY (openssl rand -base64 32),
# ANTHROPIC_API_KEY, DAILY_BUDGET_USD.
chmod 600 .env
docker compose up -d --build
docker compose --profile seed run --rm seed
./smoke-test.sh "https://$DOMAIN"
./smoke-test.sh "https://$DOMAIN" --ask     # one real question, about $0.05
```

Open only ports 80 and 443 (and SSH) in the server's firewall.

## Updates

```sh
git pull
docker compose up -d --build     # migrate runs before the new API starts
./smoke-test.sh "https://$DOMAIN"
```

## Backups

`./backup.sh` writes a `pg_dump` (custom format) into `deploy/backups/`. The sales data
is synthetic and can be regenerated; the dump matters for the audit trail. Copy dumps
off the server (they are not encrypted), and restore into a new database first: the
script prints the commands. Never delete the `db-data` volume without a backup.

## Costs and limits

- LLM spending is capped per day by `DAILY_BUDGET_USD`, counted from the audit trail
  (UTC). Analyses still running are not counted yet: the overshoot is at most
  `MAX_CONCURRENT_ANALYSES` analyses.
- Each visitor gets `ANALYSES_PER_CLIENT_PER_HOUR` analyses per rolling hour.
- Measured costs: $0.005 to $0.03 per question without explanation, $0.035 on average
  with it (Claude Opus 5.5), at most about $0.13 since the explanation's token ceiling.

## Before connecting real data

This deployment is for synthetic data. Real company data needs, at least: user
accounts and per-user permissions instead of one shared key, a decision on how long
the audit trail (which holds the questions) is kept, a review of the LLM provider's
data terms, and encrypted, tested backups. See [privacy.md](privacy.md).
