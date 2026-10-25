from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from eaa import __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


@router.get("/health")
async def health() -> HealthResponse:
    """Liveness only: the process answers. Database checks arrive with milestone 0.1."""
    return HealthResponse(status="ok", version=__version__)
