"""FastAPI application factory.

Run locally from ``backend/`` with:
    uv run uvicorn eaa.main:create_app --factory --reload
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.concurrency import run_in_threadpool

from eaa import __version__
from eaa.api import analyses, health
from eaa.api.limits import ConcurrencyLimiter, RateLimiter
from eaa.api.middleware import CorrelationIdMiddleware
from eaa.api.security import require_api_key
from eaa.config import Settings, get_settings
from eaa.observability.logs import configure_logging
from eaa.services import Services, build_services

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if app.state.services is None:
        try:
            app.state.services = await run_in_threadpool(build_services, app.state.settings)
        except Exception as error:
            # /health still answers; /analyses says what is missing (503).
            logger.warning("Analysis service unavailable: %s", error)
    yield


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.check_can_serve()
    configure_logging(settings.log_level, settings.log_format)

    # The interactive docs list every route: useful locally, not in production.
    docs_url = None if settings.app_env == "production" else "/docs"
    app = FastAPI(
        title="Enterprise AI Analyst",
        version=__version__,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=None if docs_url is None else "/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.services = services
    # Injected services (tests) are never rebuilt; otherwise /analyses retries the build.
    app.state.build_services = build_services if services is None else None
    app.state.rate_limiter = RateLimiter(settings.analyses_per_client_per_hour)
    app.state.concurrency_limiter = ConcurrencyLimiter(settings.max_concurrent_analyses)
    app.add_middleware(CorrelationIdMiddleware)
    app.include_router(health.router)
    app.include_router(
        analyses.router,
        dependencies=[Depends(require_api_key)],
        responses={401: {"description": "Missing or invalid API key."}},
    )

    if settings.api_key is None:
        logger.warning("API_KEY is not set: /analyses is open to anyone who can reach it")
    if settings.daily_budget_usd is None:
        logger.warning("DAILY_BUDGET_USD is not set: LLM spending is not capped")
    logger.info("Application created (env=%s)", settings.app_env)
    return app
