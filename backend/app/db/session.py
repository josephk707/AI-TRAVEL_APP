"""
Database connection management.

Phase 2 scope: the real Supabase/PostgreSQL schema now exists
(supabase/migrations/), so this module grows from Phase 1's
connectivity-check-only foundation into a real connection-pool manager used
by the repository layer. Still no business logic here — only connection
lifecycle and a lightweight liveness probe.

If DATABASE_URL is not set (e.g. no Supabase project configured in a given
dev environment), pool creation and connectivity checks report
"not_configured" rather than raising — the app stays honest about state
instead of pretending a database is available when none has been wired up.

SECRET SAFETY: settings.database_url is a pydantic.SecretStr (see
app/core/config.py's docstring for why). It is unwrapped via
.get_secret_value() only at the single point asyncpg actually needs the
raw DSN, never stored/logged unwrapped. Exception handling below is
deliberately generic (exception TYPE only, never str(exc)) specifically
because a connection-stage exception from asyncpg can itself embed the raw
DSN in its message — SecretStr protects the Settings object, but not an
exception raised by code operating on the unwrapped value, so this is a
second, independent safeguard, not a redundant one.
"""

from __future__ import annotations

import logging
from enum import StrEnum

import asyncpg

from app.core.config import get_settings

logger = logging.getLogger("app.db")

_pool: asyncpg.Pool | None = None


class DbStatus(StrEnum):
    OK = "ok"
    NOT_CONFIGURED = "not_configured"
    ERROR = "error"


async def create_pool() -> asyncpg.Pool | None:
    """Create the shared connection pool at application startup.

    Returns None (does not raise) if DATABASE_URL is unset or the database
    is unreachable — a missing/unreachable database must never prevent the
    API process itself from starting (graceful degradation, CLAUDE.md §9).
    Callers that actually need the database (repositories) surface their
    own clear error at query time instead.
    """
    global _pool
    settings = get_settings()

    if settings.database_url is None:
        logger.info("db_pool_skipped", extra={"reason": "not_configured"})
        return None

    try:
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url.get_secret_value(),
            min_size=1,
            max_size=5,
            timeout=5,
            command_timeout=10,
        )
        logger.info("db_pool_created")
        return _pool
    except Exception as exc:  # noqa: BLE001 - startup probe, must not crash the app
        # Exception TYPE only — never str(exc), which can embed the raw DSN.
        logger.error("db_pool_creation_failed", extra={"error_type": type(exc).__name__})
        _pool = None
        return None


async def close_pool() -> None:
    """Release the pool at application shutdown. Safe to call even if the
    pool was never created."""
    global _pool
    if _pool is not None:
        await _pool.close()
        logger.info("db_pool_closed")
        _pool = None


def get_pool() -> asyncpg.Pool | None:
    return _pool


async def check_database_connection() -> tuple[DbStatus, str | None]:
    """Lightweight, self-contained connectivity probe (`SELECT 1`) used by
    the readiness endpoint. Deliberately independent of the shared pool so
    it still gives an honest answer even if pool creation failed at
    startup. Never raises — callers decide how to represent the result.

    The returned str detail (on ERROR) is the exception TYPE NAME only,
    never str(exc) — see module docstring."""
    settings = get_settings()

    if settings.database_url is None:
        return DbStatus.NOT_CONFIGURED, None

    try:
        conn = await asyncpg.connect(settings.database_url.get_secret_value(), timeout=3)
        try:
            await conn.fetchval("SELECT 1")
        finally:
            await conn.close()
        return DbStatus.OK, None
    except Exception as exc:  # noqa: BLE001 - deliberately broad: this is a health probe
        logger.warning("database_connection_check_failed", extra={"error_type": type(exc).__name__})
        return DbStatus.ERROR, type(exc).__name__
