"""
Integration tests for /v1/quick-plans* — F22 Weekend/Local Outing Quick Plan
(IMPLEMENTATION_BLUEPRINT.md F22, AI_ARCHITECTURE.md §7). Exercised with
REAL Supabase-issued access tokens against the REAL Supabase project (same
technique as test_trips_api.py — not mocked), against the real seeded Taj
Mahal POI (Agra). Both LLM postures are exercised honestly, matching
test_trips_api.py's own precedent: the real "no LLM configured" premise no
longer holds in this environment (a real GEMINI_API_KEY is set), so the
mocked-gateway-success path is what's exercised for the AI-assisted
selection, and the deterministic fallback is exercised directly by forcing
`get_llm_gateway` to return None.

Run with:
  python scripts/run_live_tests.py tests/test_quick_plans_api.py -v
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
        "Full Supabase configuration not set — quick plans API integration "
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
    email = f"quickplan-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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


# Taj Mahal's real seeded coordinates (migration 20260825120017).
_AGRA_LAT = 27.1751
_AGRA_LNG = 78.0421


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
async def test_create_quick_plan_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/quick-plans", json={"time_available_min": 120, "lat": _AGRA_LAT, "lng": _AGRA_LNG}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# F22 — Real candidate lookup + graceful no-LLM fallback
# ---------------------------------------------------------------------------
async def test_quick_plan_falls_back_to_deterministic_selection_without_a_gateway(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import quick_plan_service

    monkeypatch.setattr(quick_plan_service, "get_llm_gateway", lambda: None)

    response = await client.post(
        "/v1/quick-plans",
        json={"time_available_min": 120, "occasion": "casual", "lat": _AGRA_LAT, "lng": _AGRA_LNG},
        headers=real_session.auth_header,
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert 1 <= len(body["items"]) <= 3
    assert any(item["poi_name"] == "Taj Mahal" for item in body["items"])


async def test_quick_plan_uses_a_real_mocked_llm_selection(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import quick_plan_service
    from app.services.quick_plan_service import _QuickPlanItem, _QuickPlanSelection

    class _FakeGateway:
        async def complete(self, messages, *, response_schema=None, config=None):
            from app.services.ai.llm_gateway import LLMResponse

            parsed = _QuickPlanSelection(
                summary="A quick heritage stop.",
                items=[_QuickPlanItem(candidate_index=0, sequence_order=0)],
            )
            return LLMResponse(text="{}", parsed=parsed, model="fake-model", output_tokens=5)

        async def complete_multimodal(self, *a, **k):
            raise NotImplementedError

        async def complete_audio(self, *a, **k):
            raise NotImplementedError

        async def embed(self, texts, *, dimensions, task_type="RETRIEVAL_DOCUMENT"):
            from app.services.ai.llm_gateway import EmbeddingResponse

            return EmbeddingResponse(
                vectors=[[0.0] * dimensions for _ in texts], dimensions=dimensions
            )

    monkeypatch.setattr(quick_plan_service, "get_llm_gateway", lambda: _FakeGateway())

    response = await client.post(
        "/v1/quick-plans",
        json={"time_available_min": 90, "lat": _AGRA_LAT, "lng": _AGRA_LNG},
        headers=real_session.auth_header,
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["summary"] == "A quick heritage stop."
    assert len(body["items"]) == 1
    assert body["items"][0]["poi_name"] == "Taj Mahal"


async def test_quick_plan_with_no_local_data_states_so_plainly(
    client: AsyncClient, real_session: _RealSession
) -> None:
    # The middle of the Atlantic Ocean has no seeded POIs and no home_region
    # fallback for a freshly created profile.
    response = await client.post(
        "/v1/quick-plans",
        json={"time_available_min": 90, "lat": 0.0, "lng": -30.0},
        headers=real_session.auth_header,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "NOT_ENOUGH_LOCAL_DATA"


async def test_invalid_time_available_is_rejected(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.post(
        "/v1/quick-plans",
        json={"time_available_min": 5, "lat": _AGRA_LAT, "lng": _AGRA_LNG},
        headers=real_session.auth_header,
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# F22 — Save to collection
# ---------------------------------------------------------------------------
async def test_save_quick_plan_to_collection(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import quick_plan_service

    monkeypatch.setattr(quick_plan_service, "get_llm_gateway", lambda: None)

    create_response = await client.post(
        "/v1/quick-plans",
        json={"time_available_min": 120, "lat": _AGRA_LAT, "lng": _AGRA_LNG},
        headers=real_session.auth_header,
    )
    plan_id = create_response.json()["data"]["id"]

    save_response = await client.post(
        f"/v1/quick-plans/{plan_id}/save-to-collection", headers=real_session.auth_header
    )
    assert save_response.status_code == 201
    body = save_response.json()["data"]
    assert body["item_count"] >= 1

    collections_response = await client.get("/v1/collections", headers=real_session.auth_header)
    assert any(c["id"] == body["collection_id"] for c in collections_response.json()["data"])


async def test_saving_someone_elses_quick_plan_returns_404(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import quick_plan_service

    monkeypatch.setattr(quick_plan_service, "get_llm_gateway", lambda: None)

    create_response = await client.post(
        "/v1/quick-plans",
        json={"time_available_min": 120, "lat": _AGRA_LAT, "lng": _AGRA_LNG},
        headers=real_session.auth_header,
    )
    plan_id = create_response.json()["data"]["id"]

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "other")
        try:
            response = await client.post(
                f"/v1/quick-plans/{plan_id}/save-to-collection", headers=other.auth_header
            )
            assert response.status_code == 404
        finally:
            await _delete_user(http, other.user_id)
