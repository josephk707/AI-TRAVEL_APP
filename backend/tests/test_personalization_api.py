"""
Integration tests for GET /v1/personalization/travel-dna — real Supabase-
issued tokens against the real backend and the real database (real
onboarding save, real favorite, real trip). Genuinely exercises the
Personalization Engine's aggregate queries against real rows, not mocks.

GEMINI_API_KEY is not configured in this environment (same honesty
discipline as test_translation_api.py) — this suite proves the real,
deterministic-template fallback path end to end; if a key is later
configured, `generated_by` will legitimately flip to "ai" and this
suite's assertions (which check the fields exist and are real, not the
exact wording) still hold.

Run with:
  python scripts/run_live_tests.py tests/test_personalization_api.py -v
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
    reason="Full Supabase configuration not set — personalization API tests skipped",
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
    email = f"dna-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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
        session = await _create_real_session(http, "dna")
        try:
            yield session
        finally:
            await _delete_user(http, session.user_id)


async def test_travel_dna_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.get("/v1/personalization/travel-dna")
    assert response.status_code == 401


async def test_travel_dna_for_a_brand_new_user_is_honest_about_knowing_nothing(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get("/v1/personalization/travel-dna", headers=real_session.auth_header)
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["trips_planned"] == 0
    assert data["places_saved"] == 0
    assert data["interests"] == []
    assert data["generated_by"] in ("template", "ai")
    # Never a placeholder/empty string — a real, controlled fallback.
    assert data["travel_personality"]
    assert data["summary"]


async def test_travel_dna_reflects_real_onboarding_answers_after_submission(
    client: AsyncClient, real_session: _RealSession
) -> None:
    onboarding_response = await client.post(
        "/v1/onboarding/responses",
        json={
            "interest_ids": [],
            "travel_style": "planned",
            "pace": "relaxed",
            "budget_bracket": "mid",
            "travel_companion": "family",
            "trip_motivation": "Trying real local food and slow mornings.",
        },
        headers=real_session.auth_header,
    )
    assert onboarding_response.status_code == 200

    response = await client.get("/v1/personalization/travel-dna", headers=real_session.auth_header)
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["travel_style"] == "planned"
    assert data["pace"] == "relaxed"
    assert data["budget_bracket"] == "mid"
    assert data["travel_companion"] == "family"
    assert data["trip_motivation"] == "Trying real local food and slow mornings."
    # The real answer actually shaped the summary, not a canned response.
    assert "family" in data["summary"].lower() or "planned" in data["summary"].lower()


async def test_travel_dna_reflects_a_real_favorited_place(
    client: AsyncClient, real_session: _RealSession
) -> None:
    search = await client.get(
        "/v1/pois/search", params={"query": "temple"}, headers=real_session.auth_header
    )
    assert search.status_code == 200
    pois = search.json()["data"]
    assert pois, (
        "Expected at least one real curated POI to exist for this assertion to be meaningful."
    )
    poi_id = pois[0]["id"]

    fav_response = await client.post(
        "/v1/favorites", json={"poi_id": poi_id}, headers=real_session.auth_header
    )
    assert fav_response.status_code == 201

    response = await client.get("/v1/personalization/travel-dna", headers=real_session.auth_header)
    data = response.json()["data"]

    assert data["places_saved"] == 1
    assert sum(data["favorite_categories"].values()) == 1
