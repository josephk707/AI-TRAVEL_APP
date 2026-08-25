"""
Integration tests for /v1/pois/* — exercised with REAL Supabase-issued
access tokens (Admin API + password grant, same technique as
test_auth_api.py/test_onboarding_api.py) against the REAL Supabase project
and its actual `pois` table (including the curated seed rows from
migration 20260825120017) — not mocked.

Skipped entirely unless DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
and SUPABASE_ANON_KEY are all set. GOOGLE_MAPS_API_KEY is NOT required for
this suite: it deliberately exercises the real, currently-true "no key
configured" degraded-mode path (this environment genuinely has no key —
see docs/PHASE_STATUS.md's Phase 5 section) rather than mocking that state.

Run with:
  python scripts/run_live_tests.py tests/test_pois_api.py -v
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
    reason=(
        "Full Supabase configuration not set — pois API integration tests "
        "skipped (needs DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, "
        "SUPABASE_ANON_KEY)"
    ),
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
    email = f"pois-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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
        session = await _create_real_session(http, "solo")
        try:
            yield session
        finally:
            await _delete_user(http, session.user_id)


# ---------------------------------------------------------------------------
# Authentication is enforced identically to every other /v1/* endpoint
# ---------------------------------------------------------------------------
async def test_search_rejects_a_request_with_no_authorization_header(client: AsyncClient) -> None:
    response = await client.get("/v1/pois/search", params={"query": "Taj Mahal"})
    assert response.status_code == 401


async def test_nearby_rejects_a_request_with_no_authorization_header(client: AsyncClient) -> None:
    response = await client.get("/v1/pois/nearby", params={"lat": 27.17, "lng": 78.04})
    assert response.status_code == 401


async def test_get_poi_rejects_a_request_with_no_authorization_header(client: AsyncClient) -> None:
    response = await client.get("/v1/pois/11111111-1111-4111-8111-111111111111")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Real, end-to-end: mobile token -> FastAPI -> real Postgres/PostGIS `pois`
# ---------------------------------------------------------------------------
async def test_search_by_text_finds_a_real_curated_seed_poi(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get(
        "/v1/pois/search", params={"query": "Taj Mahal"}, headers=real_session.auth_header
    )
    assert response.status_code == 200
    body = response.json()
    names = {poi["name"] for poi in body["data"]}
    assert "Taj Mahal" in names


async def test_search_with_no_google_key_configured_is_degraded_but_not_broken(
    client: AsyncClient, real_session: _RealSession
) -> None:
    """This environment genuinely has no GOOGLE_MAPS_API_KEY configured
    (see docs/PHASE_STATUS.md's Phase 5 section) — this test exercises that
    REAL current state, not a simulated one. A query unlikely to be
    satisfied by the small curated seed set still returns 200 with
    meta.degraded_mode=true, never a hard failure."""
    response = await client.get(
        "/v1/pois/search",
        params={"query": "some obscure place unlikely to be in the curated seed set"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["degraded_mode"] is True


async def test_search_requires_either_query_or_lat_lng(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get("/v1/pois/search", headers=real_session.auth_header)
    assert response.status_code == 400


async def test_search_rejects_an_invalid_category(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get(
        "/v1/pois/search",
        params={"query": "temple", "category": "not-a-real-category"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 400


async def test_nearby_finds_the_taj_mahal_near_its_real_coordinates(
    client: AsyncClient, real_session: _RealSession
) -> None:
    """A real PostGIS ST_DWithin query against the real database — proves
    the geospatial index/query actually works, not just that the endpoint
    returns 200."""
    response = await client.get(
        "/v1/pois/nearby",
        params={"lat": 27.1751, "lng": 78.0421, "radius_m": 5000},
        headers=real_session.auth_header,
    )
    assert response.status_code == 200
    names = {poi["name"] for poi in response.json()["data"]}
    assert "Taj Mahal" in names


async def test_nearby_far_from_any_seeded_poi_returns_an_empty_list_not_an_error(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get(
        "/v1/pois/nearby",
        # The middle of the Pacific Ocean — genuinely nowhere near any
        # seeded POI.
        params={"lat": 0.0, "lng": -160.0, "radius_m": 1000},
        headers=real_session.auth_header,
    )
    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_get_poi_returns_the_real_seeded_detail_record(
    client: AsyncClient, real_session: _RealSession
) -> None:
    search_response = await client.get(
        "/v1/pois/search", params={"query": "Red Fort"}, headers=real_session.auth_header
    )
    poi_id = search_response.json()["data"][0]["id"]

    detail_response = await client.get(f"/v1/pois/{poi_id}", headers=real_session.auth_header)

    assert detail_response.status_code == 200
    data = detail_response.json()["data"]
    assert data["name"] == "Red Fort"
    assert data["category"] == "heritage"
    assert data["source"] == "curated"
    assert data["location"]["lat"] == pytest.approx(28.6562, abs=0.001)
    assert data["location"]["lng"] == pytest.approx(77.2410, abs=0.001)


async def test_get_poi_returns_404_for_a_nonexistent_id(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get(f"/v1/pois/{uuid.uuid4()}", headers=real_session.auth_header)
    assert response.status_code == 404


async def test_get_poi_returns_404_for_a_malformed_id(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get("/v1/pois/this-is-not-a-uuid", headers=real_session.auth_header)
    assert response.status_code == 404
