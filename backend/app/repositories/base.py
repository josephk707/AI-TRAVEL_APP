"""
Repository-layer foundation.

Establishes the pattern (Router -> Service -> Repository -> Database)
required by CLAUDE.md §7 / IMPLEMENTATION_BLUEPRINT.md. Phase 2: the real
schema now exists, so this base class provides the actual shared
data-access contract every concrete repository (Phase 3+: TripsRepository,
ProfilesRepository, ...) will build on — connection acquisition, error
normalization, and resource release, all in one place instead of repeated
in every repository.

No feature endpoints are implemented against this yet (that starts in
later phases) — Phase 2 only proves the pattern works against the real
database via InterestsRepository (interests.py), a read-only lookup-table
query with no business logic attached.
"""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

from app.core.exceptions import UpstreamUnavailableError
from app.db.session import get_pool

logger = logging.getLogger("app.repositories")


class Repository:
    """Base class for data-access repositories.

    Every method acquires a connection from the shared pool, runs exactly
    one statement, and releases the connection back to the pool via
    `async with pool.acquire() as conn:` — never held longer than the
    query itself, and always released even on error (that is what the
    `async with` context manager guarantees).
    """

    def _require_pool(self) -> asyncpg.Pool:
        pool = get_pool()
        if pool is None:
            # Distinct from a query failing — the pool was never
            # established (DATABASE_URL unset, or startup connection
            # failed). Surfaced as a clear 503, never a silent empty result.
            raise UpstreamUnavailableError(
                "Database is not configured or unavailable.",
                details={"code": "DB_POOL_UNAVAILABLE"},
            )
        return pool

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        pool = self._require_pool()
        try:
            async with pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except UpstreamUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalized into one error type below
            logger.error("db_query_failed", extra={"query": query, "error": str(exc)})
            raise UpstreamUnavailableError(
                "Database query failed.", details={"code": "DB_QUERY_ERROR"}
            ) from exc

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        pool = self._require_pool()
        try:
            async with pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        except UpstreamUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("db_query_failed", extra={"query": query, "error": str(exc)})
            raise UpstreamUnavailableError(
                "Database query failed.", details={"code": "DB_QUERY_ERROR"}
            ) from exc

    async def fetchval(self, query: str, *args: Any) -> Any:
        pool = self._require_pool()
        try:
            async with pool.acquire() as conn:
                return await conn.fetchval(query, *args)
        except UpstreamUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("db_query_failed", extra={"query": query, "error": str(exc)})
            raise UpstreamUnavailableError(
                "Database query failed.", details={"code": "DB_QUERY_ERROR"}
            ) from exc
