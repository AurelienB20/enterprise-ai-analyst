# syntax=docker/dockerfile:1
# Production image of the API (and of the one-off migration and data jobs).
# Build from the backend directory:  docker build -t eaa-backend .

FROM ghcr.io/astral-sh/uv:0.13.0 AS uv

# --- Build: the locked dependencies, then the project, in a virtual environment ---
FROM python:3.12-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# --- Runtime: the venv and the migrations, no build tools, not root ---
FROM python:3.12-slim-bookworm
RUN useradd --system --uid 10001 --no-create-home eaa
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
# FORWARDED_ALLOW_IPS: who may set X-Forwarded-For (the per-client limits use it). The
# API is only reachable from the internal network (the web server), see deploy/.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    LOG_FORMAT=json \
    FORWARDED_ALLOW_IPS=127.0.0.1
USER eaa
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
# One worker: the per-client and concurrency limits are counted in memory.
CMD ["uvicorn", "eaa.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--proxy-headers", "--no-access-log"]
