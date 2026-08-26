"""
Integration tests for /v1/reviews, /v1/pois/{id}/reviews, and
/v1/admin/reviews/* — F14 Reviews & Ratings (IMPLEMENTATION_BLUEPRINT.md
F14, API_SPECIFICATION.md §12/§19). Exercised with REAL Supabase-issued
access tokens against the REAL Supabase project (same technique as
test_trips_api.py — not mocked). `profiles.role` is promoted to 'admin'
via a direct database connection to exercise the moderation endpoints,
since Supabase Auth itself has no concept of this application-level role.

Run with:
  python scripts/run_live_tests.py tests/test_reviews_api.py -v
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import asyncpg
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
        "Full Supabase configuration not set — reviews API integration "
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
    email = f"reviews-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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


async def _promote_to_admin(user_id: str) -> None:
    conn = await asyncpg.connect(DATABASE_URL, timeout=10)
    try:
        await conn.execute(
            "update public.profiles set role = 'admin' where id = $1;", uuid.UUID(user_id)
        )
    finally:
        await conn.close()


@pytest.fixture
async def real_session() -> AsyncIterator[_RealSession]:
    async with httpx.AsyncClient(timeout=15) as http:
        session = await _create_real_session(http, "a")
        try:
            yield session
        finally:
            await _delete_user(http, session.user_id)


async def _real_poi_id(client: AsyncClient, auth_header: dict[str, str]) -> str:
    response = await client.get(
        "/v1/pois/search", params={"query": "Taj Mahal"}, headers=auth_header
    )
    data = response.json()["data"]
    assert data, "Seed POI 'Taj Mahal' must exist for this test to run"
    return str(data[0]["id"])


async def _completed_trip_id(client: AsyncClient, auth_header: dict[str, str]) -> str:
    create_response = await client.post(
        "/v1/trips",
        json={"title": "Agra Trip", "destination": "Agra, India"},
        headers=auth_header,
    )
    trip_id = create_response.json()["data"]["id"]
    patch_response = await client.patch(
        f"/v1/trips/{trip_id}", json={"status": "completed"}, headers=auth_header
    )
    assert patch_response.status_code == 200
    return trip_id


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
async def test_create_review_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/reviews",
        json={"poi_id": str(uuid.uuid4()), "trip_id": str(uuid.uuid4()), "rating": 5},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# F14 — Eligibility gate
# ---------------------------------------------------------------------------
async def test_review_without_a_completed_trip_is_rejected(
    client: AsyncClient, real_session: _RealSession
) -> None:
    poi_id = await _real_poi_id(client, real_session.auth_header)
    create_response = await client.post(
        "/v1/trips",
        json={"title": "Still Planning", "destination": "Agra, India"},
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]

    response = await client.post(
        "/v1/reviews",
        json={"poi_id": poi_id, "trip_id": trip_id, "rating": 5},
        headers=real_session.auth_header,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "REVIEW_NOT_ELIGIBLE"


async def test_review_with_a_nonexistent_poi_returns_404(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _completed_trip_id(client, real_session.auth_header)
    response = await client.post(
        "/v1/reviews",
        json={"poi_id": str(uuid.uuid4()), "trip_id": trip_id, "rating": 4},
        headers=real_session.auth_header,
    )
    assert response.status_code == 404


async def test_rating_out_of_bounds_is_rejected(
    client: AsyncClient, real_session: _RealSession
) -> None:
    poi_id = await _real_poi_id(client, real_session.auth_header)
    trip_id = await _completed_trip_id(client, real_session.auth_header)
    response = await client.post(
        "/v1/reviews",
        json={"poi_id": poi_id, "trip_id": trip_id, "rating": 6},
        headers=real_session.auth_header,
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# F14 — Review submission is not immediately visible; moderation required
# ---------------------------------------------------------------------------
async def test_pending_review_is_not_visible_until_published(
    client: AsyncClient, real_session: _RealSession
) -> None:
    poi_id = await _real_poi_id(client, real_session.auth_header)
    trip_id = await _completed_trip_id(client, real_session.auth_header)

    create_response = await client.post(
        "/v1/reviews",
        json={"poi_id": poi_id, "trip_id": trip_id, "rating": 5, "review_text": "Breathtaking."},
        headers=real_session.auth_header,
    )
    assert create_response.status_code == 201
    review = create_response.json()["data"]
    assert review["status"] == "pending"

    poi_reviews = await client.get(f"/v1/pois/{poi_id}/reviews", headers=real_session.auth_header)
    assert review["id"] not in {r["id"] for r in poi_reviews.json()["data"]}


# ---------------------------------------------------------------------------
# F14/§19 — Admin moderation gate and workflow
# ---------------------------------------------------------------------------
async def test_non_admin_cannot_access_moderation_endpoints(
    client: AsyncClient, real_session: _RealSession
) -> None:
    pending_response = await client.get(
        "/v1/admin/reviews/pending", headers=real_session.auth_header
    )
    assert pending_response.status_code == 403

    kpi_response = await client.get("/v1/admin/analytics/kpis", headers=real_session.auth_header)
    assert kpi_response.status_code == 403


async def test_admin_moderation_publishes_review_and_makes_it_visible(
    client: AsyncClient, real_session: _RealSession
) -> None:
    poi_id = await _real_poi_id(client, real_session.auth_header)
    trip_id = await _completed_trip_id(client, real_session.auth_header)

    create_response = await client.post(
        "/v1/reviews",
        json={"poi_id": poi_id, "trip_id": trip_id, "rating": 5, "review_text": "Amazing sunrise."},
        headers=real_session.auth_header,
    )
    review_id = create_response.json()["data"]["id"]

    async with httpx.AsyncClient(timeout=15) as http:
        admin = await _create_real_session(http, "admin")
        try:
            await _promote_to_admin(admin.user_id)

            pending_response = await client.get(
                "/v1/admin/reviews/pending", headers=admin.auth_header
            )
            assert pending_response.status_code == 200
            assert review_id in {r["id"] for r in pending_response.json()["data"]}

            moderate_response = await client.patch(
                f"/v1/admin/reviews/{review_id}/moderate",
                json={"decision": "publish"},
                headers=admin.auth_header,
            )
            assert moderate_response.status_code == 200
            assert moderate_response.json()["data"]["status"] == "published"

            kpi_response = await client.get("/v1/admin/analytics/kpis", headers=admin.auth_header)
            assert kpi_response.status_code == 200
            assert "reviews_submitted" in kpi_response.json()["data"]
        finally:
            await _delete_user(http, admin.user_id)

    poi_reviews = await client.get(f"/v1/pois/{poi_id}/reviews", headers=real_session.auth_header)
    assert review_id in {r["id"] for r in poi_reviews.json()["data"]}


async def test_admin_can_reject_a_review_keeping_it_hidden(
    client: AsyncClient, real_session: _RealSession
) -> None:
    poi_id = await _real_poi_id(client, real_session.auth_header)
    trip_id = await _completed_trip_id(client, real_session.auth_header)

    create_response = await client.post(
        "/v1/reviews",
        json={"poi_id": poi_id, "trip_id": trip_id, "rating": 1, "review_text": "spam"},
        headers=real_session.auth_header,
    )
    review_id = create_response.json()["data"]["id"]

    async with httpx.AsyncClient(timeout=15) as http:
        admin = await _create_real_session(http, "admin2")
        try:
            await _promote_to_admin(admin.user_id)
            moderate_response = await client.patch(
                f"/v1/admin/reviews/{review_id}/moderate",
                json={"decision": "reject"},
                headers=admin.auth_header,
            )
            assert moderate_response.status_code == 200
            assert moderate_response.json()["data"]["status"] == "rejected"
        finally:
            await _delete_user(http, admin.user_id)

    poi_reviews = await client.get(f"/v1/pois/{poi_id}/reviews", headers=real_session.auth_header)
    assert review_id not in {r["id"] for r in poi_reviews.json()["data"]}
