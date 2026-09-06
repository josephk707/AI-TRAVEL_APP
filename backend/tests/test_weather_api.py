"""
Integration tests for GET /v1/weather — real Supabase-issued tokens
against the real backend, and (unlike every other provider in this
project) a genuinely real Open-Meteo call every time, since Open-Meteo's
non-commercial tier needs no API key — there is no "not configured"
degraded path to simulate here.

Run with:
  python scripts/run_live_tests.py tests/test_weather_api.py -v
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

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and SUPABASE_URL and SERVICE_ROLE_KEY and ANON_KEY),
    reason="Full Supabase configuration not set — weather API tests skipped",
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
    email = f"weather-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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
        session = await _create_real_session(http, "weather")
        try:
            yield session
        finally:
            await _delete_user(http, session.user_id)


async def test_weather_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.get("/v1/weather", params={"lat": 27.1751, "lng": 78.0421})
    assert response.status_code == 401


async def test_weather_rejects_out_of_range_coordinates(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get(
        "/v1/weather", params={"lat": 999, "lng": 78.0421}, headers=real_session.auth_header
    )
    assert response.status_code == 400


async def test_weather_returns_a_real_current_forecast_for_the_taj_mahal(
    client: AsyncClient, real_session: _RealSession
) -> None:
    """A genuinely real Open-Meteo call for a real place — proves live
    data, not just a 200 status (CLAUDE.md's own "never claim success
    based only on HTTP 200" bar)."""
    response = await client.get(
        "/v1/weather",
        params={"lat": 27.1751, "lng": 78.0421},
        headers=real_session.auth_header,
    )
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["lat"] == 27.1751
    assert data["lng"] == 78.0421

    current = data["current"]
    assert isinstance(current["temperature_c"], (int, float))
    # Agra, India in August is genuinely hot — a real sanity bound on a
    # real value, not a fabricated one.
    assert -10 <= current["temperature_c"] <= 55
    assert current["condition"] != "Unknown"
    assert isinstance(current["is_day"], bool)

    daily = data["daily"]
    assert len(daily) >= 1
    assert daily[0]["temperature_max_c"] >= daily[0]["temperature_min_c"]
    assert daily[0]["condition"] != "Unknown"
