"""
Integration tests for /v1/trips/* — F3/F4/F5/F12 — exercised with REAL
Supabase-issued access tokens against the REAL Supabase project and its
actual `trips`/`itinerary_days`/`itinerary_items`/`trip_raw_notes` tables
(same technique as test_pois_api.py/test_onboarding_api.py — not mocked).

Two LLM postures are both exercised for real, honestly:
  - "gateway not configured" (this environment's REAL current state, since
    GEMINI_API_KEY is not yet set here) — proves the documented fallback
    path against the real database, not a simulated one.
  - "gateway configured" — the Gemini SDK boundary itself is monkeypatched
    (the same boundary-mocking discipline as test_google_places_client.py)
    so the full pipeline (candidate retrieval -> mapping -> business rules
    -> real persistence) is proven end-to-end without needing a live key
    in CI. A SEPARATE, real, live-network Gemini call is exercised in
    tests/test_llm_gateway_live.py once GEMINI_API_KEY is actually set.

Run with:
  python scripts/run_live_tests.py tests/test_trips_api.py -v
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import AsyncClient

from app.core.rate_limit import reset_rate_limits_for_tests
from app.services.ai import factory as ai_factory
from app.services.ai.llm_gateway import EmbeddingResponse, LLMResponse

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and SUPABASE_URL and SERVICE_ROLE_KEY and ANON_KEY),
    reason=(
        "Full Supabase configuration not set — trips API integration tests "
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
    email = f"trips-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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
        session = await _create_real_session(http, "trips")
        try:
            yield session
        finally:
            await _delete_user(http, session.user_id)


@pytest.fixture(autouse=True)
def _reset_rate_limit_buckets() -> None:
    reset_rate_limits_for_tests()
    yield
    reset_rate_limits_for_tests()


class _FakeGateway:
    """Monkeypatched in place of the real Gemini SDK boundary — proves the
    itinerary/modification pipelines' own logic (candidate mapping,
    business-rule validation, real persistence) independent of whether a
    real GEMINI_API_KEY is configured in this environment."""

    def __init__(self, parsed_by_call: list[object]) -> None:
        self._parsed_by_call = list(parsed_by_call)
        self.calls = 0

    async def complete(self, messages, *, response_schema=None, config=None):
        parsed = self._parsed_by_call[self.calls]
        self.calls += 1
        return LLMResponse(text="{}", parsed=parsed, model="fake-model", output_tokens=42)

    async def complete_multimodal(self, *a, **k):  # pragma: no cover - unused here
        raise NotImplementedError

    async def complete_audio(self, *a, **k):  # pragma: no cover - unused here
        raise NotImplementedError

    async def embed(self, texts, *, dimensions, task_type="RETRIEVAL_DOCUMENT"):  # pragma: no cover
        return EmbeddingResponse(vectors=[[0.0] * dimensions for _ in texts], dimensions=dimensions)


# ---------------------------------------------------------------------------
# Authentication is enforced identically to every other /v1/* endpoint
# ---------------------------------------------------------------------------
async def test_create_trip_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.post("/v1/trips", json={"title": "x", "destination": "Agra, India"})
    assert response.status_code == 401


async def test_list_trips_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.get("/v1/trips")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# F12 — trip CRUD, real database
# ---------------------------------------------------------------------------
async def test_create_get_list_update_delete_trip_lifecycle(
    client: AsyncClient, real_session: _RealSession
) -> None:
    create_response = await client.post(
        "/v1/trips",
        json={
            "title": "Agra Weekend",
            "destination": "Agra, India",
            "start_date": "2026-10-10",
            "end_date": "2026-10-11",
            "budget_planned": 15000,
        },
        headers=real_session.auth_header,
    )
    assert create_response.status_code == 201
    trip = create_response.json()["data"]
    assert trip["status"] == "draft"
    assert trip["generation_status"] == "none"
    trip_id = trip["id"]

    get_response = await client.get(f"/v1/trips/{trip_id}", headers=real_session.auth_header)
    assert get_response.status_code == 200
    assert get_response.json()["data"]["title"] == "Agra Weekend"

    list_response = await client.get("/v1/trips", headers=real_session.auth_header)
    assert any(t["id"] == trip_id for t in list_response.json()["data"])

    patch_response = await client.patch(
        f"/v1/trips/{trip_id}", json={"status": "upcoming"}, headers=real_session.auth_header
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["data"]["status"] == "upcoming"

    delete_response = await client.delete(f"/v1/trips/{trip_id}", headers=real_session.auth_header)
    assert delete_response.status_code == 204

    after_delete = await client.get(f"/v1/trips/{trip_id}", headers=real_session.auth_header)
    assert after_delete.status_code == 404


async def test_another_user_cannot_access_or_update_someone_elses_trip(
    client: AsyncClient, real_session: _RealSession
) -> None:
    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "other")
        try:
            create_response = await client.post(
                "/v1/trips",
                json={"title": "Private trip", "destination": "Delhi, India"},
                headers=real_session.auth_header,
            )
            trip_id = create_response.json()["data"]["id"]

            get_response = await client.get(f"/v1/trips/{trip_id}", headers=other.auth_header)
            assert get_response.status_code == 403

            patch_response = await client.patch(
                f"/v1/trips/{trip_id}", json={"status": "cancelled"}, headers=other.auth_header
            )
            assert patch_response.status_code == 403
        finally:
            await _delete_user(http, other.user_id)


# ---------------------------------------------------------------------------
# F4 — Idea Extraction (no LLM configured in this environment — real
# graceful degradation, not simulated)
# ---------------------------------------------------------------------------
async def test_submit_notes_without_llm_still_preserves_the_raw_text(
    client: AsyncClient, real_session: _RealSession
) -> None:
    create_response = await client.post(
        "/v1/trips",
        json={"title": "Agra Trip", "destination": "Agra, India"},
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]

    notes_response = await client.post(
        f"/v1/trips/{trip_id}/notes",
        json={"raw_text": "I really want to see the Taj Mahal at sunrise."},
        headers=real_session.auth_header,
    )
    assert notes_response.status_code == 201
    body = notes_response.json()["data"]
    assert body["raw_text"] == "I really want to see the Taj Mahal at sunrise."

    list_response = await client.get(f"/v1/trips/{trip_id}/notes", headers=real_session.auth_header)
    assert len(list_response.json()["data"]) == 1


# ---------------------------------------------------------------------------
# F3 — Itinerary Generation
# ---------------------------------------------------------------------------
async def test_generate_requires_clarification_when_budget_and_dates_missing(
    client: AsyncClient, real_session: _RealSession
) -> None:
    create_response = await client.post(
        "/v1/trips",
        json={"title": "Unplanned", "destination": "Agra, India"},
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]

    generate_response = await client.post(
        f"/v1/trips/{trip_id}/itinerary/generate", json={}, headers=real_session.auth_header
    )
    assert generate_response.status_code == 422
    body = generate_response.json()
    assert body["error"]["code"] == "CLARIFICATION_NEEDED"
    assert "missing_fields" in body["error"]["details"]


async def test_generate_with_no_llm_configured_falls_back_to_real_curated_poi_scheduling(
    client: AsyncClient, real_session: _RealSession
) -> None:
    """This environment genuinely has no GEMINI_API_KEY configured — this
    exercises that REAL current state end-to-end against the real Agra
    curated POI (Taj Mahal, migration 20260825120017)."""
    if ai_factory.get_llm_gateway() is not None:
        pytest.skip(
            "GEMINI_API_KEY is configured in this environment — this test's "
            "premise (no provider configured) no longer holds; see "
            "test_llm_gateway_live.py for the real-key equivalent."
        )

    create_response = await client.post(
        "/v1/trips",
        json={
            "title": "Agra Trip",
            "destination": "Agra, India",
            "start_date": "2026-10-10",
            "end_date": "2026-10-10",
            "budget_planned": 15000,
        },
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]

    generate_response = await client.post(
        f"/v1/trips/{trip_id}/itinerary/generate",
        json={"interests": ["heritage"]},
        headers=real_session.auth_header,
    )
    assert generate_response.status_code == 200
    body = generate_response.json()
    assert body["meta"]["degraded_mode"] is True
    data = body["data"]
    assert data["generation_status"] == "fallback_used"
    all_items = [item for day in data["days"] for item in day["items"]]
    assert any(item["poi_name"] == "Taj Mahal" for item in all_items)

    trip_after = await client.get(f"/v1/trips/{trip_id}", headers=real_session.auth_header)
    assert trip_after.json()["data"]["generation_status"] == "fallback_used"


async def test_generate_with_mocked_llm_success_persists_the_structured_plan(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        headers=real_session.auth_header,
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
    fake_gateway = _FakeGateway([fake_itinerary])
    monkeypatch.setattr(itinerary_service, "get_llm_gateway", lambda: fake_gateway)

    generate_response = await client.post(
        f"/v1/trips/{trip_id}/itinerary/generate",
        json={"interests": ["heritage"]},
        headers=real_session.auth_header,
    )
    assert generate_response.status_code == 200
    body = generate_response.json()
    assert body["meta"] is None
    data = body["data"]
    assert data["generation_status"] == "succeeded"
    items = data["days"][0]["items"]
    assert len(items) == 1
    assert items[0]["poi_name"] == "Taj Mahal"
    assert items[0]["planned_start"] == "06:00"
    assert items[0]["planned_end"] == "08:30"
    assert items[0]["verify_on_arrival"] is True  # Taj Mahal seed row has no opening_hours


async def test_generate_rejects_a_hallucinated_candidate_index_without_crashing(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]

    fake_itinerary = _GeneratedItinerary(
        summary="oops",
        items=[
            _GeneratedItem(
                day_number=1, candidate_index=999, planned_start="06:00", estimated_duration_min=90
            )
        ],
    )
    monkeypatch.setattr(
        itinerary_service, "get_llm_gateway", lambda: _FakeGateway([fake_itinerary])
    )

    generate_response = await client.post(
        f"/v1/trips/{trip_id}/itinerary/generate", json={}, headers=real_session.auth_header
    )
    assert generate_response.status_code == 200
    # Every candidate_index was out of range -> zero real items -> the
    # pipeline degrades to the fallback scheduler rather than persisting
    # a hallucinated reference or crashing.
    assert generate_response.json()["meta"]["degraded_mode"] is True


# ---------------------------------------------------------------------------
# F5 — Conversational Modification
# ---------------------------------------------------------------------------
async def test_modify_with_no_llm_configured_returns_a_graceful_message(
    client: AsyncClient, real_session: _RealSession
) -> None:
    if ai_factory.get_llm_gateway() is not None:
        pytest.skip(
            "GEMINI_API_KEY is configured in this environment — this test's "
            "premise (no provider configured) no longer holds; see "
            "test_llm_gateway_live.py for the real-key equivalent."
        )

    create_response = await client.post(
        "/v1/trips",
        json={
            "title": "Agra Trip",
            "destination": "Agra, India",
            "start_date": "2026-10-10",
            "end_date": "2026-10-10",
            "budget_planned": 15000,
        },
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]

    modify_response = await client.post(
        f"/v1/trips/{trip_id}/itinerary/modify",
        json={"message": "push everything an hour later"},
        headers=real_session.auth_header,
    )
    assert modify_response.status_code == 200
    assert "temporarily unavailable" in modify_response.json()["data"]["reply"]


async def test_modify_with_mocked_llm_changes_only_the_targeted_item(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import itinerary_service, modification_service
    from app.services.itinerary_service import _GeneratedItem, _GeneratedItinerary
    from app.services.modification_service import _ItemChange, _ModificationResult

    create_response = await client.post(
        "/v1/trips",
        json={
            "title": "Agra Trip",
            "destination": "Agra, India",
            "start_date": "2026-10-10",
            "end_date": "2026-10-10",
            "budget_planned": 15000,
        },
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]

    monkeypatch.setattr(
        itinerary_service,
        "get_llm_gateway",
        lambda: _FakeGateway(
            [
                _GeneratedItinerary(
                    summary="ok",
                    items=[
                        _GeneratedItem(
                            day_number=1,
                            candidate_index=0,
                            planned_start="06:00",
                            estimated_duration_min=150,
                        )
                    ],
                )
            ]
        ),
    )
    await client.post(
        f"/v1/trips/{trip_id}/itinerary/generate", json={}, headers=real_session.auth_header
    )
    itinerary = (
        await client.get(f"/v1/trips/{trip_id}/itinerary", headers=real_session.auth_header)
    ).json()["data"]
    item_id = itinerary[0]["items"][0]["id"]

    monkeypatch.setattr(
        modification_service,
        "get_llm_gateway",
        lambda: _FakeGateway(
            [
                _ModificationResult(
                    reply="Sure — pushed it to 08:00.",
                    changes=[_ItemChange(item_id=item_id, planned_start="08:00")],
                )
            ]
        ),
    )
    modify_response = await client.post(
        f"/v1/trips/{trip_id}/itinerary/modify",
        json={"message": "start the Taj Mahal visit at 8am instead"},
        headers=real_session.auth_header,
    )
    assert modify_response.status_code == 200
    body = modify_response.json()["data"]
    assert body["changed_item_ids"] == [item_id]
    updated_item = body["days"][0]["items"][0]
    assert updated_item["planned_start"] == "08:00"


# ---------------------------------------------------------------------------
# Manual itinerary item edit (F12-adjacent)
# ---------------------------------------------------------------------------
async def test_patch_itinerary_item_recomputes_planned_end(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
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
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]
    monkeypatch.setattr(
        itinerary_service,
        "get_llm_gateway",
        lambda: _FakeGateway(
            [
                _GeneratedItinerary(
                    summary="ok",
                    items=[
                        _GeneratedItem(
                            day_number=1,
                            candidate_index=0,
                            planned_start="06:00",
                            estimated_duration_min=150,
                        )
                    ],
                )
            ]
        ),
    )
    await client.post(
        f"/v1/trips/{trip_id}/itinerary/generate", json={}, headers=real_session.auth_header
    )
    itinerary = (
        await client.get(f"/v1/trips/{trip_id}/itinerary", headers=real_session.auth_header)
    ).json()["data"]
    item_id = itinerary[0]["items"][0]["id"]

    patch_response = await client.patch(
        f"/v1/trips/{trip_id}/itinerary/items/{item_id}",
        json={"planned_start": "07:00"},
        headers=real_session.auth_header,
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()["data"]
    assert updated["planned_start"] == "07:00"
    assert updated["planned_end"] == "09:30"


# ---------------------------------------------------------------------------
# Rate limiting (H3 — documented in-process limiter for AI endpoints)
# ---------------------------------------------------------------------------
async def test_ai_endpoint_rate_limit_returns_429_after_the_documented_threshold(
    client: AsyncClient, real_session: _RealSession
) -> None:
    create_response = await client.post(
        "/v1/trips",
        json={
            "title": "Agra Trip",
            "destination": "Agra, India",
            "start_date": "2026-10-10",
            "end_date": "2026-10-10",
            "budget_planned": 15000,
        },
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]

    statuses = []
    for _ in range(11):
        response = await client.post(
            f"/v1/trips/{trip_id}/itinerary/modify",
            json={"message": "anything"},
            headers=real_session.auth_header,
        )
        statuses.append(response.status_code)

    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429
