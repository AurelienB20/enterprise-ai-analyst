"""Correlation IDs: one per request, echoed in ``X-Request-ID`` and attached to every log.

A client may send its own ID to correlate its logs with ours, but it is untrusted
input that ends up in log lines: anything that is not a short token of letters,
digits, ``-`` and ``_`` is replaced, which rules out log injection.
"""

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from eaa.observability.logs import correlation_id_var

REQUEST_ID_HEADER = "x-request-id"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")

logger = logging.getLogger(__name__)


def resolve_request_id(candidate: str | None) -> str:
    """Keep a well-formed client ID, otherwise generate one."""
    if candidate is not None and _VALID_REQUEST_ID.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


class CorrelationIdMiddleware:
    """Pure ASGI middleware, so streamed responses keep the ID until their last byte."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        raw = headers.get(REQUEST_ID_HEADER.encode("latin-1"))
        request_id = resolve_request_id(raw.decode("latin-1") if raw is not None else None)
        token = correlation_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", [])
                message["headers"].append((REQUEST_ID_HEADER.encode(), request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            # The path is logged without its query string, which may carry user input.
            logger.info(
                "%s %s -> %d",
                scope["method"],
                scope["path"],
                status_code,
                extra={"duration_ms": round((time.perf_counter() - started) * 1000, 1)},
            )
            correlation_id_var.reset(token)
