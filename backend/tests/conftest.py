from __future__ import annotations

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

import app.db.session as db_session_module
from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Runs the real app lifespan (startup/shutdown — including
    create_pool()/close_pool()), not just the bare ASGI app. A plain
    httpx.ASGITransport(app=app) never triggers lifespan events at all, so
    without LifespanManager, /readyz's pool-dependent checks would report
    "not_configured" in every test regardless of whether DATABASE_URL is
    actually set — a test-infrastructure gap, not a real behavior, found
    while making tests/test_health.py adaptive to real environment state
    (see docs/PHASE_STATUS.md Phase 2 "known limitations")."""
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def _reset_pool() -> None:
    # If a prior test left a real pool open, close it properly rather than
    # just discarding the reference (which would leak open connections) —
    # then null it out so the next test starts from a genuinely clean slate.
    if db_session_module._pool is not None:
        await db_session_module._pool.close()
    db_session_module._pool = None


@pytest.fixture(autouse=True)
async def _reset_db_pool_state():
    """The connection pool is deliberately module-level global state
    (app/db/session.py), so it can leak across tests within the same
    pytest process — e.g. a live-database test creating a real pool would
    otherwise cause a LATER, unrelated Phase-1 test (which assumes "no pool
    exists yet") to see a real pool and fail. Reset before AND after every
    test so each one starts and ends with a clean slate, independent of
    what ran before or after it."""
    await _reset_pool()
    yield
    await _reset_pool()
