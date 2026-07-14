"""Liveness (/healthz) and readiness (/readyz) endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from kanuni_api.config import Settings, get_settings
from kanuni_api.db.health import check_database_connection

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    """Response body for the liveness check."""

    status: str


class ReadinessResponse(BaseModel):
    """Response body for the readiness check, detailing each dependency probed."""

    status: str
    checks: dict[str, bool]


@router.get("/healthz", response_model=LivenessResponse)
async def get_liveness() -> LivenessResponse:
    """Report whether the process is alive.

    Returns:
        A body indicating the process is running. Never checks downstream
        dependencies — that is the job of /readyz.
    """
    return LivenessResponse(status="ok")


@router.get("/readyz", response_model=ReadinessResponse)
async def get_readiness(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadinessResponse:
    """Report whether the service is ready to accept traffic.

    Checks database connectivity. Embedding-model readiness will be added
    once retrieval is implemented (Phase 2).

    Args:
        response: The outgoing response, whose status code is set to 503
            when a dependency is not ready.
        settings: Application settings, providing the database DSN.

    Returns:
        A body listing the result of each dependency check.
    """
    database_ready = await check_database_connection(settings.database_url)
    checks = {"database": database_ready}
    if not all(checks.values()):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="not_ready", checks=checks)
    return ReadinessResponse(status="ok", checks=checks)
