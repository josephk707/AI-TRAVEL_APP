"""
Integration tests for /v1/trips/{id}/disruptions* — F20 Dynamic Itinerary
Re-Adaptation Engine (IMPLEMENTATION_BLUEPRINT.md F20, AI_ARCHITECTURE.md
§8, resolving ARCHITECTURE_REVIEW.md H2 — see app/schemas/disruption.py's
module docstring). Exercised with REAL Supabase-issued access tokens
against the REAL Supabase project (same technique as test_trips_api.py —
not mocked). The real itinerary is generated via the established
mocked-LLM-gateway technique (this environment has a genuine
GEMINI_API_KEY, so the no-key fallback premise doesn't hold). The
`weather_service.check_adverse_weather` boundary itself is monkeypatched
— this project has no `WEATHER_API_KEY` configured in this environment,
so a real live provider call cannot be exercised, but the full pipeline
around it (candidate lookup, disruption_events persistence, accept/dismiss,
itinerary mutation) is proven end-to-end against the real database.

Run with:
  python scripts/run_live_tests.py tests/test_disruptions_api.py -v
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
        "Full Supabase configuration not set — disruptions API integration "
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
    email = f"disruption-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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
) -> tuple[str, str]:
    """Returns (trip_id, itinerary_item_id) with a real itinerary item
    scheduled against the real seeded Taj Mahal POI."""
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

    itinerary = (await client.get(f"/v1/trips/{trip_id}/itinerary", headers=auth_header)).json()[
        "data"
    ]
    item_id = itinerary[0]["items"][0]["id"]
    return trip_id, item_id


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
async def test_list_disruptions_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.get(f"/v1/trips/{uuid.uuid4()}/disruptions")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# F20 — Real weather-triggered disruption detection
# ---------------------------------------------------------------------------
async def test_check_creates_a_disruption_when_weather_is_adverse(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import disruption_service

    trip_id, item_id = await _trip_with_real_itinerary(
        client, real_session.auth_header, monkeypatch
    )

    async def _adverse(lat, lng, date_iso):
        return True

    monkeypatch.setattr(disruption_service.weather_service, "check_adverse_weather", _adverse)

    check_response = await client.post(
        f"/v1/trips/{trip_id}/disruptions/check", headers=real_session.auth_header
    )
    assert check_response.status_code == 200
    events = check_response.json()["data"]
    assert len(events) == 1
    assert events[0]["trigger_type"] == "weather"
    assert events[0]["itinerary_item_id"] == item_id
    assert events[0]["status"] == "proposed"
    assert "reason" in events[0]["proposal"]

    list_response = await client.get(
        f"/v1/trips/{trip_id}/disruptions", headers=real_session.auth_header
    )
    assert len(list_response.json()["data"]) == 1


async def test_check_is_a_noop_when_weather_is_fine(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import disruption_service

    trip_id, _ = await _trip_with_real_itinerary(client, real_session.auth_header, monkeypatch)

    async def _fine(lat, lng, date_iso):
        return False

    monkeypatch.setattr(disruption_service.weather_service, "check_adverse_weather", _fine)

    check_response = await client.post(
        f"/v1/trips/{trip_id}/disruptions/check", headers=real_session.auth_header
    )
    assert check_response.status_code == 200
    assert check_response.json()["data"] == []


async def test_repeated_checks_do_not_duplicate_an_open_proposal(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import disruption_service

    trip_id, _ = await _trip_with_real_itinerary(client, real_session.auth_header, monkeypatch)

    async def _adverse(lat, lng, date_iso):
        return True

    monkeypatch.setattr(disruption_service.weather_service, "check_adverse_weather", _adverse)

    await client.post(f"/v1/trips/{trip_id}/disruptions/check", headers=real_session.auth_header)
    second_check = await client.post(
        f"/v1/trips/{trip_id}/disruptions/check", headers=real_session.auth_header
    )
    assert second_check.json()["data"] == []

    list_response = await client.get(
        f"/v1/trips/{trip_id}/disruptions", headers=real_session.auth_header
    )
    assert len(list_response.json()["data"]) == 1


# ---------------------------------------------------------------------------
# F20 — Accept/dismiss, never applied without explicit confirmation
# ---------------------------------------------------------------------------
async def test_dismissing_a_disruption_leaves_the_itinerary_untouched(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import disruption_service

    trip_id, item_id = await _trip_with_real_itinerary(
        client, real_session.auth_header, monkeypatch
    )

    async def _adverse(lat, lng, date_iso):
        return True

    monkeypatch.setattr(disruption_service.weather_service, "check_adverse_weather", _adverse)
    check_response = await client.post(
        f"/v1/trips/{trip_id}/disruptions/check", headers=real_session.auth_header
    )
    event_id = check_response.json()["data"][0]["id"]

    before = (
        await client.get(f"/v1/trips/{trip_id}/itinerary", headers=real_session.auth_header)
    ).json()["data"][0]["items"][0]["poi_id"]

    resolve_response = await client.post(
        f"/v1/trips/{trip_id}/disruptions/{event_id}/resolve",
        json={"decision": "dismiss"},
        headers=real_session.auth_header,
    )
    assert resolve_response.status_code == 200
    assert resolve_response.json()["data"]["status"] == "dismissed"

    after = (
        await client.get(f"/v1/trips/{trip_id}/itinerary", headers=real_session.auth_header)
    ).json()["data"][0]["items"][0]["poi_id"]
    assert after == before


async def test_resolving_an_already_resolved_disruption_is_rejected(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import disruption_service

    trip_id, _ = await _trip_with_real_itinerary(client, real_session.auth_header, monkeypatch)

    async def _adverse(lat, lng, date_iso):
        return True

    monkeypatch.setattr(disruption_service.weather_service, "check_adverse_weather", _adverse)
    check_response = await client.post(
        f"/v1/trips/{trip_id}/disruptions/check", headers=real_session.auth_header
    )
    event_id = check_response.json()["data"][0]["id"]

    await client.post(
        f"/v1/trips/{trip_id}/disruptions/{event_id}/resolve",
        json={"decision": "dismiss"},
        headers=real_session.auth_header,
    )
    second_resolve = await client.post(
        f"/v1/trips/{trip_id}/disruptions/{event_id}/resolve",
        json={"decision": "dismiss"},
        headers=real_session.auth_header,
    )
    assert second_resolve.status_code == 409


async def test_another_user_cannot_check_list_or_resolve_disruptions(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_id, _ = await _trip_with_real_itinerary(client, real_session.auth_header, monkeypatch)

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "other")
        try:
            list_response = await client.get(
                f"/v1/trips/{trip_id}/disruptions", headers=other.auth_header
            )
            assert list_response.status_code == 403

            check_response = await client.post(
                f"/v1/trips/{trip_id}/disruptions/check", headers=other.auth_header
            )
            assert check_response.status_code == 403
        finally:
            await _delete_user(http, other.user_id)
