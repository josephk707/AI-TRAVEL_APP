"""
Liveness and readiness routes.

Route handlers only parse/authorize/delegate — all logic lives in
app.services.health_service, per CLAUDE.md §7.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.schemas.common import Envelope
from app.services import health_service
from app.services.health_service import LivenessResult, ReadinessResult

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=Envelope[LivenessResult])
async def healthz() -> Envelope[LivenessResult]:
    """Liveness probe — process is up and serving requests. No dependency
    checks here on purpose; a dependency outage must not make the process
    look dead (that's what /readyz is for)."""
    return Envelope(data=health_service.get_liveness())


@router.get("/readyz", response_model=Envelope[ReadinessResult])
async def readyz(response: Response) -> Envelope[ReadinessResult]:
    """Readiness probe — is this instance actually able to serve real
    traffic right now. Reports (not fails on) an unconfigured database,
    since Phase 1 environments legitimately have none yet."""
    result = await health_service.get_readiness()
    if result.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Envelope(data=result)
