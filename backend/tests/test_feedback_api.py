"""
Integration tests for /v1/trips/{id}/feedback — F17 Post-Trip Feedback
Capture (IMPLEMENTATION_BLUEPRINT.md F17, API_SPECIFICATION.md §17).
Exercised with REAL Supabase-issued access tokens against the REAL
Supabase project (same technique as test_trips_api.py — not mocked).

Run with:
  python scripts/run_live_tests.py tests/test_feedback_api.py -v
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
        "Full Supabase configuration not set — feedback API integration "
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
    email = f"feedback-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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


async def _new_trip(client: AsyncClient, auth_header: dict[str, str]) -> str:
    response = await client.post(
        "/v1/trips",
        json={"title": "Agra Trip", "destination": "Agra, India"},
        headers=auth_header,
    )
    return str(response.json()["data"]["id"])


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
async def test_submit_feedback_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.post(f"/v1/trips/{uuid.uuid4()}/feedback", json={})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# F17 — Feedback submission, real database, purely additive (never blocks)
# ---------------------------------------------------------------------------
async def test_submit_free_text_feedback_only(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header)
    response = await client.post(
        f"/v1/trips/{trip_id}/feedback",
        json={"free_text": "Loved the itinerary pacing!"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["trip_id"] == trip_id
    assert body["signals_recorded"] == 1


async def test_submit_per_stop_signals_and_free_text_together(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`feedback_signals.itinerary_item_id` has a real FK to
    `itinerary_items(id)` — uses the same mocked-LLM technique as
    test_trips_api.py to populate two real items rather than passing
    fabricated ids that would fail the constraint."""
    from app.services import itinerary_service
    from app.services.ai.llm_gateway import EmbeddingResponse, LLMResponse
    from app.services.itinerary_service import _GeneratedItem, _GeneratedItinerary

    class _FakeGateway:
        def __init__(self, parsed: object) -> None:
            self._parsed = parsed

        async def complete(self, messages, *, response_schema=None, config=None):
            return LLMResponse(text="{}", parsed=self._parsed, model="fake-model", output_tokens=1)

        async def complete_multimodal(self, *a, **k):
            raise NotImplementedError

        async def complete_audio(self, *a, **k):
            raise NotImplementedError

        async def embed(self, texts, *, dimensions, task_type="RETRIEVAL_DOCUMENT"):
            return EmbeddingResponse(
                vectors=[[0.0] * dimensions for _ in texts], dimensions=dimensions
            )

    create_response = await client.post(
        "/v1/trips",
        json={
            "title": "Agra Trip",
            "destination": "Agra, India",
            "start_date": "2026-10-10",
            "end_date": "2026-10-11",
            "budget_planned": 15000,
        },
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]

    # Only one real POI is seeded for Agra (Taj Mahal) — both items
    # reference the same real candidate (index 0) across two different
    # days, which is enough to prove two distinct, real itinerary_item
    # rows exist for the FK-backed feedback signal.
    fake_itinerary = _GeneratedItinerary(
        summary="ok",
        items=[
            _GeneratedItem(
                day_number=1, candidate_index=0, planned_start="06:00", estimated_duration_min=90
            ),
            _GeneratedItem(
                day_number=2, candidate_index=0, planned_start="10:00", estimated_duration_min=90
            ),
        ],
    )
    monkeypatch.setattr(itinerary_service, "get_llm_gateway", lambda: _FakeGateway(fake_itinerary))
    await client.post(
        f"/v1/trips/{trip_id}/itinerary/generate", json={}, headers=real_session.auth_header
    )
    itinerary = (
        await client.get(f"/v1/trips/{trip_id}/itinerary", headers=real_session.auth_header)
    ).json()["data"]
    all_items = [i for day in itinerary for i in day["items"]]
    item_id_a = all_items[0]["id"]
    item_id_b = all_items[1]["id"]

    response = await client.post(
        f"/v1/trips/{trip_id}/feedback",
        json={
            "stops": [
                {"itinerary_item_id": item_id_a, "signal": "thumbs_up"},
                {"itinerary_item_id": item_id_b, "signal": "thumbs_down"},
            ],
            "free_text": "The second stop felt rushed.",
        },
        headers=real_session.auth_header,
    )
    assert response.status_code == 201
    assert response.json()["data"]["signals_recorded"] == 3


async def test_submitting_empty_feedback_is_allowed_and_never_blocks(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header)
    response = await client.post(
        f"/v1/trips/{trip_id}/feedback", json={}, headers=real_session.auth_header
    )
    assert response.status_code == 201
    assert response.json()["data"]["signals_recorded"] == 0


async def test_invalid_signal_value_is_rejected(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header)
    response = await client.post(
        f"/v1/trips/{trip_id}/feedback",
        json={"stops": [{"itinerary_item_id": str(uuid.uuid4()), "signal": "meh"}]},
        headers=real_session.auth_header,
    )
    assert response.status_code == 400


async def test_feedback_on_nonexistent_trip_returns_404(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.post(
        f"/v1/trips/{uuid.uuid4()}/feedback",
        json={"free_text": "orphaned"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 404


async def test_another_user_cannot_submit_feedback_on_someone_elses_trip(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header)

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "other")
        try:
            response = await client.post(
                f"/v1/trips/{trip_id}/feedback",
                json={"free_text": "not mine"},
                headers=other.auth_header,
            )
            assert response.status_code == 403
        finally:
            await _delete_user(http, other.user_id)
