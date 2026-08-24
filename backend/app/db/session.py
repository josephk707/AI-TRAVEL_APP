"""
Database connection foundation ONLY.

Phase 1 scope, per docs/PHASE_STATUS.md governance for this phase:
  - establish the ability to check connectivity to Postgres/Supabase
  - do NOT define any business schema, tables, or ORM models here
  - do NOT create fake data or fake users

The actual schema (docs/DATABASE_SCHEMA.md) is implemented in Phase 2.

If DATABASE_URL is not set (e.g. no Supabase project provisioned yet in a
given dev environment), connectivity checks report "not_configured" rather
than raising — this keeps the app honest about state instead of pretending
a database is available when none has been wired up.
"""

from __future__ import annotations

import logging
from enum import StrEnum

import asyncpg

from app.core.config import get_settings

logger = logging.getLogger("app.db")


class DbStatus(StrEnum):
    OK = "ok"
    NOT_CONFIGURED = "not_configured"
    ERROR = "error"


async def check_database_connection() -> tuple[DbStatus, str | None]:
    """Attempt a lightweight connectivity check (`SELECT 1`).

    Returns (status, error_detail). Never raises — callers (e.g. the
    readiness endpoint) decide how to represent this to the client.
    """
    settings = get_settings()

    if not settings.database_url:
        return DbStatus.NOT_CONFIGURED, None

    try:
        conn = await asyncpg.connect(settings.database_url, timeout=3)
        try:
            await conn.fetchval("SELECT 1")
        finally:
            await conn.close()
        return DbStatus.OK, None
    except Exception as exc:  # noqa: BLE001 - deliberately broad: this is a health probe
        logger.warning("database_connection_check_failed", extra={"error": str(exc)})
        return DbStatus.ERROR, str(exc)
