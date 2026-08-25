"""
Repository/connection-lifecycle tests that don't require a live database —
they prove the FAILURE paths (no pool configured) are handled correctly,
per this phase's §14 requirement to prove the backend "can... handle
connection failures, handle database errors, close/release resources
correctly" using the real repository architecture (not a mock database).

These tests explicitly force the "DATABASE_URL unset" scenario via
monkeypatching app.db.session.get_settings, rather than assuming the
ambient environment happens to have no DATABASE_URL configured — this
suite must pass the same way whether or not the developer running it has a
real Supabase project configured in backend/.env (Phase 2 onward legitimately
does). See docs/PHASE_STATUS.md Phase 2 "known limitations" for why this
distinction matters here specifically.

The SUCCESS path (a real query against a real migrated table) is proven
separately in tests/test_live_database.py, which is skipped unless
DATABASE_URL is actually set — see that file for why a live database is
required for that half of the proof and cannot be faked here.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.exceptions import UpstreamUnavailableError
from app.db.session import close_pool, create_pool, get_pool
from app.repositories.interests_repository import InterestsRepository


@pytest.fixture(autouse=True)
def _force_database_url_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test in this file needs a Settings instance with
    database_url=None, regardless of what backend/.env actually contains
    on this machine. _env_file=None skips reading the .env file entirely
    (not just process env vars), so this is genuinely independent of
    ambient state."""
    monkeypatch.setattr(
        "app.db.session.get_settings",
        lambda: Settings(_env_file=None, database_url=None),
    )


async def test_create_pool_returns_none_when_database_url_unset() -> None:
    pool = await create_pool()
    assert pool is None
    assert get_pool() is None


async def test_close_pool_is_safe_when_never_created() -> None:
    assert get_pool() is None
    await close_pool()  # must not raise
    assert get_pool() is None


async def test_repository_raises_typed_error_when_pool_unavailable() -> None:
    assert get_pool() is None
    repo = InterestsRepository()

    with pytest.raises(UpstreamUnavailableError) as exc_info:
        await repo.list_interests()

    assert exc_info.value.status_code == 503
    assert exc_info.value.details.get("code") == "DB_POOL_UNAVAILABLE"
