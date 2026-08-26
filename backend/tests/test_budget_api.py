"""
Integration tests for /v1/trips/{id}/budget, /expenses — F15 Budget
Estimate (IMPLEMENTATION_BLUEPRINT.md F15, API_SPECIFICATION.md §14).
Exercised with REAL Supabase-issued access tokens against the REAL
Supabase project (same technique as test_trips_api.py — not mocked).

Run with:
  python scripts/run_live_tests.py tests/test_budget_api.py -v
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
        "Full Supabase configuration not set — budget API integration "
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
    email = f"budget-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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


async def _new_trip(client: AsyncClient, auth_header: dict[str, str], budget: float = 10000) -> str:
    response = await client.post(
        "/v1/trips",
        json={"title": "Agra Trip", "destination": "Agra, India", "budget_planned": budget},
        headers=auth_header,
    )
    return str(response.json()["data"]["id"])


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
async def test_get_budget_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.get(f"/v1/trips/{uuid.uuid4()}/budget")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# F15 — Budget summary and expense logging, real database
# ---------------------------------------------------------------------------
async def test_budget_summary_for_a_new_trip_starts_at_zero(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header, budget=10000)
    response = await client.get(f"/v1/trips/{trip_id}/budget", headers=real_session.auth_header)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["planned_budget"] == 10000
    assert body["total_spent"] == 0
    assert body["over_budget"] is False
    assert body["expenses"] == []


async def test_log_expense_updates_summary_and_persists(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header, budget=10000)

    log_response = await client.post(
        f"/v1/trips/{trip_id}/expenses",
        json={"category": "food", "amount": 500, "currency": "INR"},
        headers=real_session.auth_header,
    )
    assert log_response.status_code == 201
    expense = log_response.json()["data"]
    assert expense["amount"] == 500
    assert expense["category"] == "food"
    assert log_response.json()["meta"] is None

    summary_response = await client.get(
        f"/v1/trips/{trip_id}/budget", headers=real_session.auth_header
    )
    body = summary_response.json()["data"]
    assert body["total_spent"] == 500
    assert len(body["expenses"]) == 1


async def test_expense_over_10_percent_tolerance_flags_over_budget_but_never_blocks(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header, budget=1000)

    response = await client.post(
        f"/v1/trips/{trip_id}/expenses",
        json={"category": "lodging", "amount": 1200, "currency": "INR"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 201
    assert response.json()["meta"]["over_budget"] is True

    summary_response = await client.get(
        f"/v1/trips/{trip_id}/budget", headers=real_session.auth_header
    )
    assert summary_response.json()["data"]["over_budget"] is True


async def test_invalid_expense_category_is_rejected(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header)
    response = await client.post(
        f"/v1/trips/{trip_id}/expenses",
        json={"category": "invalid_category", "amount": 100, "currency": "INR"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 400


async def test_negative_or_zero_expense_amount_is_rejected(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header)
    response = await client.post(
        f"/v1/trips/{trip_id}/expenses",
        json={"category": "food", "amount": 0, "currency": "INR"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 400


async def test_another_user_cannot_view_or_log_expenses_on_someone_elses_trip(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header)

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "other")
        try:
            get_response = await client.get(
                f"/v1/trips/{trip_id}/budget", headers=other.auth_header
            )
            assert get_response.status_code == 403

            post_response = await client.post(
                f"/v1/trips/{trip_id}/expenses",
                json={"category": "food", "amount": 100, "currency": "INR"},
                headers=other.auth_header,
            )
            assert post_response.status_code == 403
        finally:
            await _delete_user(http, other.user_id)
