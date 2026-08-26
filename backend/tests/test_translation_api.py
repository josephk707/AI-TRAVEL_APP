"""
Integration tests for /v1/translate/text — real Supabase-issued tokens
against the real backend. This environment genuinely has no GEMINI_API_KEY
configured yet, so the "not configured -> 503" path is exercised for real,
not simulated (same honesty discipline as test_pois_api.py's degraded-mode
test). Once a real key is configured, this same suite's "not configured"
test would need updating — flagged here deliberately, matching the
precedent in test_pois_api.py's own comment.

Run with:
  python scripts/run_live_tests.py tests/test_translation_api.py -v
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import AsyncClient

from app.services.ai import factory as ai_factory

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and SUPABASE_URL and SERVICE_ROLE_KEY and ANON_KEY),
    reason="Full Supabase configuration not set — translation API tests skipped",
)


def _admin_headers() -> dict[str, str]:
    return {"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"}


class _RealSession:
    def __init__(self, user_id: str, access_token: str) -> None:
        self.user_id = user_id
        self.access_token = access_token

    @property
    def auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


async def _create_real_session(http: httpx.AsyncClient, tag: str) -> _RealSession:
    email = f"translate-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
    password = uuid.uuid4().hex
    create_response = await http.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=_admin_headers(),
        json={"email": email, "email_confirm": True, "password": password},
    )
    create_response.raise_for_status()
    user_id = create_response.json()["id"]
    token_response = await http.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON_KEY},
        json={"email": email, "password": password},
    )
    token_response.raise_for_status()
    return _RealSession(user_id, token_response.json()["access_token"])


async def _delete_user(http: httpx.AsyncClient, user_id: str) -> None:
    response = await http.delete(
        f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}", headers=_admin_headers()
    )
    if response.status_code not in (200, 204, 404):
        response.raise_for_status()


@pytest.fixture
async def real_session() -> AsyncIterator[_RealSession]:
    async with httpx.AsyncClient(timeout=15) as http:
        session = await _create_real_session(http, "translate")
        try:
            yield session
        finally:
            await _delete_user(http, session.user_id)


async def test_translate_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/translate/text", json={"text": "hello", "target_language": "Hindi"}
    )
    assert response.status_code == 401


async def test_translate_rejects_empty_text(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.post(
        "/v1/translate/text",
        json={"text": "", "target_language": "Hindi"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 400


async def test_translate_with_no_gemini_key_configured_returns_503_not_a_crash(
    client: AsyncClient, real_session: _RealSession
) -> None:
    """This environment genuinely has no GEMINI_API_KEY configured — proves
    the real current graceful-degradation state, not a simulated one."""
    assert ai_factory.get_llm_gateway() is None, "this test assumes no real Gemini key is set"

    response = await client.post(
        "/v1/translate/text",
        json={"text": "Where is the nearest railway station?", "target_language": "Hindi"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "UPSTREAM_UNAVAILABLE"
