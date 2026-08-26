from __future__ import annotations

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

import app.db.session as db_session_module
from app.main import app
from app.services.ai.factory import get_llm_gateway


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


@pytest.fixture(autouse=True)
def _reset_llm_gateway_cache():
    """`get_llm_gateway()` is `@lru_cache`d — correct for production (one
    process, one long-lived event loop), but a real, reproducible bug in
    THIS test environment: `pytest-asyncio`'s default config gives every
    test function its own event loop, while the cache keeps the SAME
    `GeminiAdapter` (and the httpx async connection pool it holds
    internally) alive across the whole pytest process. Once that adapter's
    connections were opened against one test's event loop, ANY later test
    that reaches it — even indirectly, even a test that doesn't itself
    call Gemini — hits a real `RuntimeError: Event loop is closed` when
    httpcore tries to close the stale connection. Found by actually running
    the suite with a real `GEMINI_API_KEY` configured (Phase 6
    certification pass), not assumed. Clearing the cache before/after every
    test forces a fresh adapter bound to that test's own loop each time."""
    get_llm_gateway.cache_clear()
    yield
    get_llm_gateway.cache_clear()
