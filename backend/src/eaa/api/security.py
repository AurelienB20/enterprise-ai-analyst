"""Optional API key. The frontend proxy will add it server-side; it is never trusted to
identify a user, only to keep the API (and its LLM budget) closed to strangers."""

import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from eaa.config import Settings


def require_api_key(request: Request, x_api_key: Annotated[str | None, Header()] = None) -> None:
    settings: Settings = request.app.state.settings
    if settings.api_key is None:
        return
    expected = settings.api_key.get_secret_value()
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid API key.")
