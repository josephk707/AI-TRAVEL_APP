"""
Health/readiness business logic.

Kept out of the route handler (app/api/v1/health.py) per CLAUDE.md §7:
"Business logic belongs in service layers, not route handlers." This is a
deliberately simple service, but it establishes the pattern every later
service follows.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.db.session import DbStatus, check_database_connection


class LivenessResult(BaseModel):
    status: str
    app_name: str
    app_version: str
    environment: str


class ReadinessChecks(BaseModel):
    config: str
    database: str


class ReadinessResult(BaseModel):
    status: str
    checks: ReadinessChecks


def get_liveness() -> LivenessResult:
    settings: Settings = get_settings()
    return LivenessResult(
        status="ok",
        app_name=settings.app_name,
        app_version=settings.app_version,
        environment=settings.environment,
    )


async def get_readiness() -> ReadinessResult:
    """Readiness is honest about partial configuration: a Phase-1
    environment with no Supabase project yet is reported as
    `database: not_configured`, not silently treated as healthy and not
    treated as a failure either — only an actual connection ERROR fails
    readiness."""
    db_status, _detail = await check_database_connection()

    checks = ReadinessChecks(config="ok", database=db_status.value)
    overall = "ready" if db_status != DbStatus.ERROR else "not_ready"

    return ReadinessResult(status=overall, checks=checks)
