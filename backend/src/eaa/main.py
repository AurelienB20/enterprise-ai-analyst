"""FastAPI application factory.

Run locally from ``backend/`` with:
    uv run uvicorn eaa.main:create_app --factory --reload
"""

import logging

from fastapi import FastAPI

from eaa import __version__
from eaa.api import health
from eaa.api.middleware import CorrelationIdMiddleware
from eaa.config import Settings, get_settings
from eaa.observability.logs import configure_logging

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    # The interactive docs list every route: useful locally, not in production.
    docs_url = None if settings.app_env == "production" else "/docs"
    app = FastAPI(
        title="Enterprise AI Analyst",
        version=__version__,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=None if docs_url is None else "/openapi.json",
    )
    app.state.settings = settings
    app.add_middleware(CorrelationIdMiddleware)
    app.include_router(health.router)

    logger.info("Application created (env=%s)", settings.app_env)
    return app
