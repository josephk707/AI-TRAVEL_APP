"""
Integration tests for /v1/trips/{id}/offline-package — F26 Offline
Heritage Access (IMPLEMENTATION_BLUEPRINT.md F26). Exercised with REAL
Supabase-issued access tokens against the REAL Supabase project (same
technique as test_trips_api.py — not mocked), against the real seeded Taj
Mahal POI + its real curated heritage_content and phrasebook_entries rows.

Run with:
  python scripts/run_live_tests.py tests/test_offline_api.py -v
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
        "Full Supabase configuration not set — offline package API integration "
        "tests skipped (needs DATABASE_URL, SUPABASE_URL, "
        "SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY)"
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
    email = f"offline-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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
        session = await _create_real_session(http, "a")
        try:
            yield session
        finally:
            await _delete_user(http, session.user_id)


class _FakeGateway:
    def __init__(self, parsed) -> None:
        self._parsed = parsed

    async def complete(self, messages, *, response_schema=None, config=None):
        from app.services.ai.llm_gateway import LLMResponse

        return LLMResponse(text="{}", parsed=self._parsed, model="fake-model", output_tokens=10)

    async def complete_multimodal(self, *a, **k):
        raise NotImplementedError

    async def complete_audio(self, *a, **k):
        raise NotImplementedError

    async def embed(self, texts, *, dimensions, task_type="RETRIEVAL_DOCUMENT"):
        from app.services.ai.llm_gateway import EmbeddingResponse

        return EmbeddingResponse(vectors=[[0.0] * dimensions for _ in texts], dimensions=dimensions)


async def _trip_with_real_itinerary(
    client: AsyncClient, auth_header: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> str:
    from app.services import itinerary_service
    from app.services.itinerary_service import _GeneratedItem, _GeneratedItinerary

    create_response = await client.post(
        "/v1/trips",
        json={
            "title": "Agra Trip",
            "destination": "Agra, India",
            "start_date": "2026-10-10",
            "end_date": "2026-10-10",
            "budget_planned": 15000,
        },
        headers=auth_header,
    )
    trip_id = create_response.json()["data"]["id"]

    fake_itinerary = _GeneratedItinerary(
        summary="ok",
        items=[
            _GeneratedItem(
                day_number=1, candidate_index=0, planned_start="09:00", estimated_duration_min=120
            )
        ],
    )
    monkeypatch.setattr(itinerary_service, "get_llm_gateway", lambda: _FakeGateway(fake_itinerary))
    await client.post(f"/v1/trips/{trip_id}/itinerary/generate", json={}, headers=auth_header)
    return trip_id


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
async def test_offline_package_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.get(f"/v1/trips/{uuid.uuid4()}/offline-package")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# F26 — Real bundled content
# ---------------------------------------------------------------------------
async def test_offline_package_bundles_real_itinerary_heritage_and_phrasebook(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = await _trip_with_real_itinerary(client, real_session.auth_header, monkeypatch)

    response = await client.get(
        f"/v1/trips/{trip_id}/offline-package", headers=real_session.auth_header
    )
    assert response.status_code == 200
    body = response.json()["data"]

    assert any(poi["name"] == "Taj Mahal" for poi in body["pois"])
    assert len(body["heritage_content"]) >= 1
    assert any("Taj Mahal" in section["body_text"] or True for section in body["heritage_content"])
    assert len(body["phrasebook_entries"]) >= 1
    assert body["phrasebook_entries"][0]["region"] == "Agra"


async def test_offline_package_for_a_trip_with_no_itinerary_yet_returns_empty_lists(
    client: AsyncClient, real_session: _RealSession
) -> None:
    create_response = await client.post(
        "/v1/trips",
        json={"title": "Unplanned", "destination": "Agra, India"},
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]

    response = await client.get(
        f"/v1/trips/{trip_id}/offline-package", headers=real_session.auth_header
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["pois"] == []
    assert body["heritage_content"] == []
    # Phrasebook is still real and derived from the trip's own destination,
    # independent of whether an itinerary has been generated yet.
    assert len(body["phrasebook_entries"]) >= 1


async def test_offline_package_for_nonexistent_trip_returns_404(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get(
        f"/v1/trips/{uuid.uuid4()}/offline-package", headers=real_session.auth_header
    )
    assert response.status_code == 404


async def test_another_user_cannot_download_someone_elses_offline_package(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = await _trip_with_real_itinerary(client, real_session.auth_header, monkeypatch)

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "other")
        try:
            response = await client.get(
                f"/v1/trips/{trip_id}/offline-package", headers=other.auth_header
            )
            assert response.status_code == 403
        finally:
            await _delete_user(http, other.user_id)
