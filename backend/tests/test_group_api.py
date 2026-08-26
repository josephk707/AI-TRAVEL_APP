"""
Integration tests for /v1/trips/{id}/invite, /v1/trips/invite/{token}/accept,
/v1/trips/{id}/members/*, /v1/trips/{id}/itinerary/reconcile — F19
Group/Collaborative Trip Planning (IMPLEMENTATION_BLUEPRINT.md F19,
API_SPECIFICATION.md §13). Exercised with REAL Supabase-issued access
tokens against the REAL Supabase project (same technique as
test_trips_api.py — not mocked). Reconciliation is exercised with the
same mocked-LLM-gateway technique already established there, since
GEMINI_API_KEY is genuinely configured in this environment.

Run with:
  python scripts/run_live_tests.py tests/test_group_api.py -v
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
        "Full Supabase configuration not set — group planning API integration "
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
    email = f"group-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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
async def organiser() -> AsyncIterator[_RealSession]:
    async with httpx.AsyncClient(timeout=15) as http:
        session = await _create_real_session(http, "organiser")
        try:
            yield session
        finally:
            await _delete_user(http, session.user_id)


async def _new_trip(client: AsyncClient, auth_header: dict[str, str]) -> str:
    response = await client.post(
        "/v1/trips",
        json={
            "title": "Group Agra Trip",
            "destination": "Agra, India",
            "start_date": "2026-10-10",
            "end_date": "2026-10-10",
            "budget_planned": 20000,
        },
        headers=auth_header,
    )
    return str(response.json()["data"]["id"])


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
async def test_create_invite_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.post(f"/v1/trips/{uuid.uuid4()}/invite", json={"method": "link"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# F19 — Invite lifecycle, real database
# ---------------------------------------------------------------------------
async def test_organiser_creates_invite_and_member_accepts(
    client: AsyncClient, organiser: _RealSession
) -> None:
    trip_id = await _new_trip(client, organiser.auth_header)

    invite_response = await client.post(
        f"/v1/trips/{trip_id}/invite", json={"method": "link"}, headers=organiser.auth_header
    )
    assert invite_response.status_code == 201
    invite = invite_response.json()["data"]
    assert invite["status"] == "pending"
    token = invite["token"]

    async with httpx.AsyncClient(timeout=15) as http:
        member = await _create_real_session(http, "member")
        try:
            accept_response = await client.post(
                f"/v1/trips/invite/{token}/accept", headers=member.auth_header
            )
            assert accept_response.status_code == 200
            body = accept_response.json()["data"]
            assert body["trip_id"] == trip_id
            assert body["joined"] is True

            members_response = await client.get(
                f"/v1/trips/{trip_id}/members", headers=organiser.auth_header
            )
            assert any(m["user_id"] == member.user_id for m in members_response.json()["data"])

            # Accepted membership grants real trip access to the new member.
            get_trip_response = await client.get(f"/v1/trips/{trip_id}", headers=member.auth_header)
            assert get_trip_response.status_code == 200
        finally:
            await _delete_user(http, member.user_id)


async def test_only_organiser_can_create_an_invite(
    client: AsyncClient, organiser: _RealSession
) -> None:
    trip_id = await _new_trip(client, organiser.auth_header)

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "other")
        try:
            response = await client.post(
                f"/v1/trips/{trip_id}/invite", json={"method": "link"}, headers=other.auth_header
            )
            assert response.status_code == 403
        finally:
            await _delete_user(http, other.user_id)


async def test_accepting_the_same_invite_twice_is_rejected(
    client: AsyncClient, organiser: _RealSession
) -> None:
    trip_id = await _new_trip(client, organiser.auth_header)
    invite_response = await client.post(
        f"/v1/trips/{trip_id}/invite", json={"method": "link"}, headers=organiser.auth_header
    )
    token = invite_response.json()["data"]["token"]

    async with httpx.AsyncClient(timeout=15) as http:
        member = await _create_real_session(http, "member2")
        try:
            first = await client.post(
                f"/v1/trips/invite/{token}/accept", headers=member.auth_header
            )
            assert first.status_code == 200

            second = await client.post(
                f"/v1/trips/invite/{token}/accept", headers=member.auth_header
            )
            assert second.status_code == 409
        finally:
            await _delete_user(http, member.user_id)


async def test_accepting_an_invalid_token_returns_404(
    client: AsyncClient, organiser: _RealSession
) -> None:
    response = await client.post(
        "/v1/trips/invite/not-a-real-token/accept", headers=organiser.auth_header
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# F19 — Preferences
# ---------------------------------------------------------------------------
async def test_member_can_submit_own_preferences_but_not_someone_elses(
    client: AsyncClient, organiser: _RealSession
) -> None:
    trip_id = await _new_trip(client, organiser.auth_header)
    invite_response = await client.post(
        f"/v1/trips/{trip_id}/invite", json={"method": "link"}, headers=organiser.auth_header
    )
    token = invite_response.json()["data"]["token"]

    async with httpx.AsyncClient(timeout=15) as http:
        member = await _create_real_session(http, "member3")
        try:
            await client.post(f"/v1/trips/invite/{token}/accept", headers=member.auth_header)

            own_response = await client.post(
                f"/v1/trips/{trip_id}/members/{member.user_id}/preferences",
                json={"interests": ["heritage"], "budget_max": 15000},
                headers=member.auth_header,
            )
            assert own_response.status_code == 200
            assert own_response.json()["data"]["interests"] == ["heritage"]

            other_response = await client.post(
                f"/v1/trips/{trip_id}/members/{organiser.user_id}/preferences",
                json={"interests": ["food"]},
                headers=member.auth_header,
            )
            assert other_response.status_code == 403
        finally:
            await _delete_user(http, member.user_id)


# ---------------------------------------------------------------------------
# F19 — Reconciliation (AI_ARCHITECTURE.md §9 rule-based-first merge)
# ---------------------------------------------------------------------------
async def test_reconcile_requires_organiser_and_at_least_one_preference(
    client: AsyncClient, organiser: _RealSession
) -> None:
    trip_id = await _new_trip(client, organiser.auth_header)

    no_prefs_response = await client.post(
        f"/v1/trips/{trip_id}/itinerary/reconcile", headers=organiser.auth_header
    )
    assert no_prefs_response.status_code == 422
    assert no_prefs_response.json()["error"]["code"] == "NO_PREFERENCES_SUBMITTED"

    async with httpx.AsyncClient(timeout=15) as http:
        member = await _create_real_session(http, "member4")
        try:
            invite_response = await client.post(
                f"/v1/trips/{trip_id}/invite",
                json={"method": "link"},
                headers=organiser.auth_header,
            )
            token = invite_response.json()["data"]["token"]
            await client.post(f"/v1/trips/invite/{token}/accept", headers=member.auth_header)

            forbidden_response = await client.post(
                f"/v1/trips/{trip_id}/itinerary/reconcile", headers=member.auth_header
            )
            assert forbidden_response.status_code == 403
        finally:
            await _delete_user(http, member.user_id)


async def test_reconcile_merges_preferences_and_reports_conflicts(
    client: AsyncClient, organiser: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import itinerary_service
    from app.services.itinerary_service import _GeneratedItem, _GeneratedItinerary

    trip_id = await _new_trip(client, organiser.auth_header)

    async with httpx.AsyncClient(timeout=15) as http:
        member = await _create_real_session(http, "member5")
        try:
            invite_response = await client.post(
                f"/v1/trips/{trip_id}/invite",
                json={"method": "link"},
                headers=organiser.auth_header,
            )
            token = invite_response.json()["data"]["token"]
            await client.post(f"/v1/trips/invite/{token}/accept", headers=member.auth_header)

            await client.post(
                f"/v1/trips/{trip_id}/members/{organiser.user_id}/preferences",
                json={"interests": ["heritage"], "budget_max": 20000},
                headers=organiser.auth_header,
            )
            await client.post(
                f"/v1/trips/{trip_id}/members/{member.user_id}/preferences",
                json={"interests": ["food"], "budget_max": 10000},
                headers=member.auth_header,
            )

            class _FakeGateway:
                async def complete(self, messages, *, response_schema=None, config=None):
                    from app.services.ai.llm_gateway import LLMResponse

                    parsed = _GeneratedItinerary(
                        summary="A reconciled plan.",
                        items=[
                            _GeneratedItem(
                                day_number=1,
                                candidate_index=0,
                                planned_start="09:00",
                                estimated_duration_min=120,
                            )
                        ],
                    )
                    return LLMResponse(
                        text="{}", parsed=parsed, model="fake-model", output_tokens=10
                    )

                async def complete_multimodal(self, *a, **k):
                    raise NotImplementedError

                async def complete_audio(self, *a, **k):
                    raise NotImplementedError

                async def embed(self, texts, *, dimensions, task_type="RETRIEVAL_DOCUMENT"):
                    from app.services.ai.llm_gateway import EmbeddingResponse

                    return EmbeddingResponse(
                        vectors=[[0.0] * dimensions for _ in texts], dimensions=dimensions
                    )

            monkeypatch.setattr(itinerary_service, "get_llm_gateway", lambda: _FakeGateway())

            reconcile_response = await client.post(
                f"/v1/trips/{trip_id}/itinerary/reconcile", headers=organiser.auth_header
            )
            assert reconcile_response.status_code == 200
            body = reconcile_response.json()["data"]
            assert organiser.user_id in body["included_member_ids"]
            assert member.user_id in body["included_member_ids"]
            budget_conflicts = [c for c in body["conflicts"] if c["field"] == "budget"]
            assert len(budget_conflicts) == 1
            assert (
                "10000.0" in budget_conflicts[0]["resolution"]
                or "10000" in budget_conflicts[0]["resolution"]
            )
        finally:
            await _delete_user(http, member.user_id)
