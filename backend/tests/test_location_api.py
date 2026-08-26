"""
Integration tests for /v1/trips/{id}/location/*, /nearby — F7 Real-Time
Location Companion & Arrival Notifications (IMPLEMENTATION_BLUEPRINT.md
F7, API_SPECIFICATION.md §6). Exercised with REAL Supabase-issued access
tokens against the REAL Supabase project and its actual PostGIS
`ST_DWithin`/`ST_Distance` geofencing — not simulated. The itinerary used
to exercise arrival detection is generated via the real, documented
no-LLM-configured fallback path (same technique as
test_trips_api.py::test_generate_with_no_llm_configured_falls_back_to_real_curated_poi_scheduling),
against the real seeded Taj Mahal POI.

Run with:
  python scripts/run_live_tests.py tests/test_location_api.py -v
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
        "Full Supabase configuration not set — location API integration "
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
    email = f"location-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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


async def _real_taj_mahal_poi(client: AsyncClient, auth_header: dict[str, str]) -> dict:
    response = await client.get(
        "/v1/pois/search", params={"query": "Taj Mahal"}, headers=auth_header
    )
    data = response.json()["data"]
    assert data, "Seed POI 'Taj Mahal' must exist for this test to run"
    return data[0]


class _FakeGateway:
    """Monkeypatched in place of the real Gemini SDK boundary (same
    technique as test_trips_api.py's own `_FakeGateway`) so itinerary
    generation deterministically schedules candidate_index=0 (the real
    seeded Taj Mahal row — PoisRepository.search_text's own
    heritage-flagship-first ordering) regardless of whether this
    environment happens to have a real GEMINI_API_KEY configured."""

    def __init__(self, parsed: object) -> None:
        self._parsed = parsed

    async def complete(self, messages, *, response_schema=None, config=None):
        from app.services.ai.llm_gateway import LLMResponse

        return LLMResponse(text="{}", parsed=self._parsed, model="fake-model", output_tokens=42)

    async def complete_multimodal(self, *a, **k):  # pragma: no cover - unused here
        raise NotImplementedError

    async def complete_audio(self, *a, **k):  # pragma: no cover - unused here
        raise NotImplementedError

    async def embed(self, texts, *, dimensions, task_type="RETRIEVAL_DOCUMENT"):  # pragma: no cover
        from app.services.ai.llm_gateway import EmbeddingResponse

        return EmbeddingResponse(vectors=[[0.0] * dimensions for _ in texts], dimensions=dimensions)


async def _trip_with_generated_itinerary(
    client: AsyncClient, auth_header: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> str:
    """Populates a real itinerary item against the real seeded Taj Mahal
    POI, deterministically, independent of ambient GEMINI_API_KEY state."""
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
        summary="A sunrise Taj Mahal visit.",
        items=[
            _GeneratedItem(
                day_number=1, candidate_index=0, planned_start="06:00", estimated_duration_min=150
            )
        ],
    )
    monkeypatch.setattr(itinerary_service, "get_llm_gateway", lambda: _FakeGateway(fake_itinerary))

    generate_response = await client.post(
        f"/v1/trips/{trip_id}/itinerary/generate",
        json={"interests": ["heritage"]},
        headers=auth_header,
    )
    assert generate_response.status_code == 200
    assert generate_response.json()["data"]["generation_status"] == "succeeded"
    return trip_id


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
async def test_location_ping_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.post(
        f"/v1/trips/{uuid.uuid4()}/location/ping", json={"lat": 27.17, "lng": 78.04}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# BR-014 — Consent gate is checked FIRST, before any location write
# ---------------------------------------------------------------------------
async def test_location_ping_without_consent_is_refused(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = await _trip_with_generated_itinerary(client, real_session.auth_header, monkeypatch)
    response = await client.post(
        f"/v1/trips/{trip_id}/location/ping",
        json={"lat": 27.1751, "lng": 78.0421},
        headers=real_session.auth_header,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "LOCATION_CONSENT_REQUIRED"


async def test_consent_can_be_granted_and_then_ping_succeeds(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = await _trip_with_generated_itinerary(client, real_session.auth_header, monkeypatch)

    consent_response = await client.post(
        f"/v1/trips/{trip_id}/location/consent",
        json={"consent": True},
        headers=real_session.auth_header,
    )
    assert consent_response.status_code == 200
    assert consent_response.json()["data"]["consent"] is True

    ping_response = await client.post(
        f"/v1/trips/{trip_id}/location/ping",
        json={"lat": 10.0, "lng": 10.0},
        headers=real_session.auth_header,
    )
    assert ping_response.status_code == 200


# ---------------------------------------------------------------------------
# F7 — Real PostGIS arrival detection
# ---------------------------------------------------------------------------
async def test_ping_at_the_exact_poi_coordinates_triggers_real_arrival_detection(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = await _trip_with_generated_itinerary(client, real_session.auth_header, monkeypatch)
    poi = await _real_taj_mahal_poi(client, real_session.auth_header)

    await client.post(
        f"/v1/trips/{trip_id}/location/consent",
        json={"consent": True},
        headers=real_session.auth_header,
    )

    ping_response = await client.post(
        f"/v1/trips/{trip_id}/location/ping",
        json={"lat": poi["location"]["lat"], "lng": poi["location"]["lng"]},
        headers=real_session.auth_header,
    )
    assert ping_response.status_code == 200
    body = ping_response.json()["data"]
    assert body["arrival_event"] is not None
    assert body["arrival_event"]["poi_name"] == "Taj Mahal"

    itinerary_response = await client.get(
        f"/v1/trips/{trip_id}/itinerary", headers=real_session.auth_header
    )
    all_items = [i for day in itinerary_response.json()["data"] for i in day["items"]]
    arrived_item = next(
        i for i in all_items if i["id"] == body["arrival_event"]["itinerary_item_id"]
    )
    assert arrived_item["status"] == "completed"


async def test_ping_far_from_any_itinerary_item_reports_no_arrival(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = await _trip_with_generated_itinerary(client, real_session.auth_header, monkeypatch)
    await client.post(
        f"/v1/trips/{trip_id}/location/consent",
        json={"consent": True},
        headers=real_session.auth_header,
    )
    # Middle of the Atlantic Ocean — nowhere near any curated POI.
    response = await client.post(
        f"/v1/trips/{trip_id}/location/ping",
        json={"lat": 0.0, "lng": -30.0},
        headers=real_session.auth_header,
    )
    assert response.status_code == 200
    assert response.json()["data"]["arrival_event"] is None


# ---------------------------------------------------------------------------
# FR-006 — Manual location fallback (GPS denied) bypasses the consent gate
# ---------------------------------------------------------------------------
async def test_manual_location_confirmation_never_requires_consent(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = await _trip_with_generated_itinerary(client, real_session.auth_header, monkeypatch)
    poi = await _real_taj_mahal_poi(client, real_session.auth_header)

    response = await client.post(
        f"/v1/trips/{trip_id}/location/manual",
        json={"poi_id": poi["id"]},
        headers=real_session.auth_header,
    )
    assert response.status_code == 200
    assert response.json()["data"]["arrival_event"]["poi_name"] == "Taj Mahal"


async def test_manual_location_for_a_nonexistent_poi_returns_404(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = await _trip_with_generated_itinerary(client, real_session.auth_header, monkeypatch)
    response = await client.post(
        f"/v1/trips/{trip_id}/location/manual",
        json={"poi_id": str(uuid.uuid4())},
        headers=real_session.auth_header,
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# F7 — Nearby recommendations
# ---------------------------------------------------------------------------
async def test_get_nearby_returns_real_recommendations_near_a_known_poi(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = await _trip_with_generated_itinerary(client, real_session.auth_header, monkeypatch)
    poi = await _real_taj_mahal_poi(client, real_session.auth_header)

    response = await client.get(
        f"/v1/trips/{trip_id}/nearby",
        params={"lat": poi["location"]["lat"], "lng": poi["location"]["lng"]},
        headers=real_session.auth_header,
    )
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------
async def test_another_user_cannot_ping_or_read_someone_elses_trip_location(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id = await _trip_with_generated_itinerary(client, real_session.auth_header, monkeypatch)
    await client.post(
        f"/v1/trips/{trip_id}/location/consent",
        json={"consent": True},
        headers=real_session.auth_header,
    )

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "other")
        try:
            ping_response = await client.post(
                f"/v1/trips/{trip_id}/location/ping",
                json={"lat": 27.17, "lng": 78.04},
                headers=other.auth_header,
            )
            assert ping_response.status_code == 403

            nearby_response = await client.get(
                f"/v1/trips/{trip_id}/nearby",
                params={"lat": 27.17, "lng": 78.04},
                headers=other.auth_header,
            )
            assert nearby_response.status_code == 403

            consent_response = await client.post(
                f"/v1/trips/{trip_id}/location/consent",
                json={"consent": True},
                headers=other.auth_header,
            )
            assert consent_response.status_code == 403
        finally:
            await _delete_user(http, other.user_id)
