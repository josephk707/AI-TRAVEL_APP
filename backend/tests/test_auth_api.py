"""
Integration tests for /v1/auth/* — exercised with REAL Supabase-issued
access tokens (never a locally fabricated JWT, per this phase's explicit
requirement). A token is obtained the same way the mobile app eventually
will: create a real ephemeral user via the Admin API, then perform a real
password-grant login against Supabase Auth to get a genuine, correctly
signed access token — then send that token to OUR OWN FastAPI app exactly
as a real client would.

Skipped entirely unless DATABASE_URL, SUPABASE_URL,
SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY and SUPABASE_JWT_SECRET are
all set.

Run with (all five required):
  DATABASE_URL=... SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... \
    SUPABASE_ANON_KEY=... SUPABASE_JWT_SECRET=... \
    pytest tests/test_auth_api.py -v
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import AsyncClient

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and SUPABASE_URL and SERVICE_ROLE_KEY and ANON_KEY and JWT_SECRET),
    reason=(
        "Full Supabase Auth configuration not set — auth API integration tests "
        "skipped (needs DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, "
        "SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET)"
    ),
)


def _admin_headers() -> dict[str, str]:
    return {"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"}


class _RealSession:
    def __init__(self, user_id: str, access_token: str, refresh_token: str) -> None:
        self.user_id = user_id
        self.access_token = access_token
        self.refresh_token = refresh_token

    @property
    def auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


async def _create_real_session(http: httpx.AsyncClient, tag: str) -> _RealSession:
    email = f"auth-api-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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
    body = token_response.json()
    return _RealSession(user_id, body["access_token"], body["refresh_token"])


async def _delete_user(http: httpx.AsyncClient, user_id: str) -> None:
    response = await http.delete(
        f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}", headers=_admin_headers()
    )
    if response.status_code not in (200, 204, 404):
        response.raise_for_status()


@pytest.fixture
async def real_session() -> AsyncIterator[_RealSession]:
    async with httpx.AsyncClient(timeout=15) as http:
        session = await _create_real_session(http, "solo")
        try:
            yield session
        finally:
            await _delete_user(http, session.user_id)


@pytest.fixture
async def two_real_sessions() -> AsyncIterator[tuple[_RealSession, _RealSession]]:
    async with httpx.AsyncClient(timeout=15) as http:
        session_a = await _create_real_session(http, "a")
        session_b = await _create_real_session(http, "b")
        try:
            yield session_a, session_b
        finally:
            await _delete_user(http, session_a.user_id)
            await _delete_user(http, session_b.user_id)


# ---------------------------------------------------------------------------
# Protected-endpoint rejection — no fabricated identity gets through
# ---------------------------------------------------------------------------
async def test_get_me_rejects_a_request_with_no_authorization_header(client: AsyncClient) -> None:
    response = await client.get("/v1/auth/me")
    assert response.status_code == 401


async def test_get_me_rejects_a_syntactically_invalid_token(client: AsyncClient) -> None:
    response = await client.get("/v1/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"})
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "UNAUTHORIZED"


# ---------------------------------------------------------------------------
# Real end-to-end chain: mobile token -> FastAPI verification -> Postgres
# ---------------------------------------------------------------------------
async def test_session_bootstrap_loads_the_trigger_created_profile(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.post("/v1/auth/session/bootstrap", headers=real_session.auth_header)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["profile"]["id"] == real_session.user_id
    # The on_auth_user_created trigger (DATABASE_SCHEMA.md §3) already
    # created this row before this request could ever be made — the
    # defensive create-fallback path should never trigger in normal
    # operation.
    assert body["created"] is False


async def test_get_me_returns_this_exact_users_own_profile(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get("/v1/auth/me", headers=real_session.auth_header)
    assert response.status_code == 200
    profile = response.json()["data"]
    assert profile["id"] == real_session.user_id
    assert profile["role"] == "traveller"


async def test_two_different_real_users_get_two_different_profiles(
    client: AsyncClient, two_real_sessions: tuple[_RealSession, _RealSession]
) -> None:
    session_a, session_b = two_real_sessions

    response_a = await client.get("/v1/auth/me", headers=session_a.auth_header)
    response_b = await client.get("/v1/auth/me", headers=session_b.auth_header)

    profile_a = response_a.json()["data"]
    profile_b = response_b.json()["data"]
    assert profile_a["id"] == session_a.user_id
    assert profile_b["id"] == session_b.user_id
    assert profile_a["id"] != profile_b["id"]


# ---------------------------------------------------------------------------
# Real logout: proves an actual server-side revocation happened, not just
# a 200 response — the session's refresh token must genuinely stop working.
# ---------------------------------------------------------------------------
async def test_logout_actually_revokes_the_refresh_token(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.post("/v1/auth/logout", headers=real_session.auth_header)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "logged_out"

    async with httpx.AsyncClient(timeout=15) as http:
        refresh_response = await http.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
            headers={"apikey": ANON_KEY},
            json={"refresh_token": real_session.refresh_token},
        )

    assert refresh_response.status_code in (400, 401), (
        "REGRESSION: the refresh token obtained before /v1/auth/logout still "
        "works afterward — logout is not actually revoking the session server-side."
    )
