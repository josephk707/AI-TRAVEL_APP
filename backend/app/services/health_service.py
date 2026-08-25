"""
Health/readiness business logic.

Kept out of the route handler (app/api/v1/health.py) per CLAUDE.md §7:
"Business logic belongs in service layers, not route handlers."

Phase 2 addition: readiness now also proves the application SCHEMA is
actually present and queryable (not just that Postgres itself accepts a
`SELECT 1`) — by going through the real repository layer against the
`interests` lookup table seeded in migration 20260825120002. This is the
concrete proof required by this phase's §14 ("Backend Integration"): the
backend can connect, execute a safe query via the repository pattern,
handle errors, and release resources — without implementing any feature
endpoint.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.db.session import DbStatus, check_database_connection, get_pool
from app.repositories.interests_repository import InterestsRepository


class LivenessResult(BaseModel):
    status: str
    app_name: str
    app_version: str
    environment: str


class ReadinessChecks(BaseModel):
    config: str
    database: str
    schema_status: str  # not named `schema` — that shadows BaseModel's own `schema` attribute


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


async def _check_schema() -> str:
    """ "ok" only if a real query against a real migrated table succeeds
    and returns the expected seeded row count. "not_configured" mirrors
    the database check (no pool = nothing to check yet). "error" covers
    everything else — including "the pool is up but migrations haven't
    been applied yet" (a missing-table error), which is deliberately NOT
    the same as "not_configured"."""
    if get_pool() is None:
        return DbStatus.NOT_CONFIGURED.value

    try:
        count = await InterestsRepository().count_interests()
        return DbStatus.OK.value if count > 0 else DbStatus.ERROR.value
    except AppError:
        return DbStatus.ERROR.value


async def get_readiness() -> ReadinessResult:
    """Readiness is honest about partial configuration: an environment
    with no Supabase project yet is reported as `not_configured`, not
    silently treated as healthy and not treated as a failure either — only
    an actual connection/query ERROR fails readiness."""
    db_status, _detail = await check_database_connection()
    schema_status = await _check_schema()

    checks = ReadinessChecks(config="ok", database=db_status.value, schema_status=schema_status)
    overall = (
        "ready"
        if db_status != DbStatus.ERROR and schema_status != DbStatus.ERROR.value
        else "not_ready"
    )

    return ReadinessResult(status=overall, checks=checks)
