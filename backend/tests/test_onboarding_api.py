"""
Integration tests for /v1/onboarding/* — exercised with REAL Supabase-issued
access tokens (Admin API + password grant, same technique as
test_auth_api.py) against the REAL Supabase project and its actual
`profiles`/`interests`/`profile_interests` tables — not mocked.

Skipped entirely unless DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
and SUPABASE_ANON_KEY are all set (same requirement as test_auth_api.py; no
JWT secret needed — see app/core/security.py).

Run with:
  python scripts/run_live_tests.py tests/test_onboarding_api.py -v
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
        "Full Supabase configuration not set — onboarding API integration tests "
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
    email = f"onboarding-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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
async def test_get_interests_rejects_a_request_with_no_authorization_header(
    client: AsyncClient,
) -> None:
    response = await client.get("/v1/onboarding/interests")
    assert response.status_code == 401


async def test_get_status_rejects_a_request_with_no_authorization_header(
    client: AsyncClient,
) -> None:
    response = await client.get("/v1/onboarding/status")
    assert response.status_code == 401


async def test_submit_responses_rejects_a_request_with_no_authorization_header(
    client: AsyncClient,
) -> None:
    response = await client.post("/v1/onboarding/responses", json={"interest_ids": []})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Real, end-to-end: mobile token -> FastAPI -> Postgres (profiles + profile_interests)
# ---------------------------------------------------------------------------
async def test_get_interests_returns_the_real_curated_catalog(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get("/v1/onboarding/interests", headers=real_session.auth_header)
    assert response.status_code == 200
    interests = response.json()["data"]
    assert len(interests) >= 12  # the curated seed set from migration 20260825120002
    slugs = {item["slug"] for item in interests}
    assert "heritage" in slugs
    assert "food" in slugs


async def test_status_is_not_completed_for_a_brand_new_user(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get("/v1/onboarding/status", headers=real_session.auth_header)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["onboarding_completed"] is False
    assert body["onboarding_completed_at"] is None


async def test_submit_responses_persists_to_the_real_database_and_marks_complete(
    client: AsyncClient, real_session: _RealSession
) -> None:
    interests_response = await client.get(
        "/v1/onboarding/interests", headers=real_session.auth_header
    )
    two_real_ids = [row["id"] for row in interests_response.json()["data"][:2]]

    submit_response = await client.post(
        "/v1/onboarding/responses",
        headers=real_session.auth_header,
        json={
            "interest_ids": two_real_ids,
            "travel_style": "planned",
            "pace": "relaxed",
            "budget_bracket": "mid",
        },
    )
    assert submit_response.status_code == 200
    body = submit_response.json()
    assert body["meta"]["saved"] is True
    data = body["data"]
    assert data["onboarding_completed"] is True
    assert data["onboarding_completed_at"] is not None
    assert sorted(data["interest_ids"]) == sorted(two_real_ids)
    assert data["travel_style"] == "planned"
    assert data["pace"] == "relaxed"
    assert data["budget_bracket"] == "mid"

    # REGRESSION-PROOF: read it back via a completely separate request,
    # proving this is real persisted state, not just an echo of the request.
    status_response = await client.get("/v1/onboarding/status", headers=real_session.auth_header)
    status_body = status_response.json()["data"]
    assert status_body["onboarding_completed"] is True

    me_response = await client.get("/v1/auth/me", headers=real_session.auth_header)
    profile = me_response.json()["data"]
    assert profile["travel_style"] == "planned"
    assert profile["pace"] == "relaxed"
    assert profile["budget_bracket"] == "mid"
    assert profile["onboarding_completed_at"] is not None


async def test_submit_responses_with_empty_selection_still_marks_complete(
    client: AsyncClient, real_session: _RealSession
) -> None:
    """The FR-003 "skip" alternative flow's shape: no interests, no
    preferences — but the caller must still be able to mark onboarding done
    so it is never re-shown."""
    response = await client.post(
        "/v1/onboarding/responses",
        headers=real_session.auth_header,
        json={"interest_ids": []},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["onboarding_completed"] is True
    assert data["interest_ids"] == []


async def test_submit_responses_rejects_an_unknown_interest_id(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.post(
        "/v1/onboarding/responses",
        headers=real_session.auth_header,
        json={"interest_ids": [999999]},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_INTEREST_IDS"


async def test_submit_responses_rejects_an_invalid_pace_value(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.post(
        "/v1/onboarding/responses",
        headers=real_session.auth_header,
        json={"interest_ids": [], "pace": "warp-speed"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_resubmitting_onboarding_replaces_the_previous_interest_selection(
    client: AsyncClient, real_session: _RealSession
) -> None:
    interests_response = await client.get(
        "/v1/onboarding/interests", headers=real_session.auth_header
    )
    all_ids = [row["id"] for row in interests_response.json()["data"]]

    await client.post(
        "/v1/onboarding/responses",
        headers=real_session.auth_header,
        json={"interest_ids": all_ids[:3]},
    )
    second = await client.post(
        "/v1/onboarding/responses",
        headers=real_session.auth_header,
        json={"interest_ids": all_ids[3:5]},
    )

    assert sorted(second.json()["data"]["interest_ids"]) == sorted(all_ids[3:5])
