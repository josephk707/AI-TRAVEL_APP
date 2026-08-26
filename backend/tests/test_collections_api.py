"""
Integration tests for /v1/favorites, /v1/collections — F13 Collections &
Favourites (IMPLEMENTATION_BLUEPRINT.md F13, API_SPECIFICATION.md §11).
Exercised with REAL Supabase-issued access tokens against the REAL Supabase
project (same technique as test_trips_api.py — not mocked).

Run with:
  python scripts/run_live_tests.py tests/test_collections_api.py -v
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
        "Full Supabase configuration not set — collections API integration "
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
    email = f"collections-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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


async def _real_poi_id(client: AsyncClient, auth_header: dict[str, str]) -> str:
    response = await client.get(
        "/v1/pois/search", params={"query": "Taj Mahal"}, headers=auth_header
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data, "Seed POI 'Taj Mahal' must exist for this test to run"
    return str(data[0]["id"])


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
async def test_add_favorite_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.post("/v1/favorites", json={"poi_id": str(uuid.uuid4())})
    assert response.status_code == 401


async def test_list_favorites_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.get("/v1/favorites")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# F13 — Favorites lifecycle, real database
# ---------------------------------------------------------------------------
async def test_add_list_and_remove_favorite_real_poi(
    client: AsyncClient, real_session: _RealSession
) -> None:
    poi_id = await _real_poi_id(client, real_session.auth_header)

    add_response = await client.post(
        "/v1/favorites", json={"poi_id": poi_id}, headers=real_session.auth_header
    )
    assert add_response.status_code == 201
    assert add_response.json()["data"]["favorited"] is True

    list_response = await client.get("/v1/favorites", headers=real_session.auth_header)
    assert list_response.status_code == 200
    favorite_ids = {f["poi_id"] for f in list_response.json()["data"]}
    assert poi_id in favorite_ids

    remove_response = await client.delete(
        f"/v1/favorites/{poi_id}", headers=real_session.auth_header
    )
    assert remove_response.status_code == 204

    list_after = await client.get("/v1/favorites", headers=real_session.auth_header)
    assert poi_id not in {f["poi_id"] for f in list_after.json()["data"]}


async def test_adding_the_same_favorite_twice_is_idempotent(
    client: AsyncClient, real_session: _RealSession
) -> None:
    poi_id = await _real_poi_id(client, real_session.auth_header)

    first = await client.post(
        "/v1/favorites", json={"poi_id": poi_id}, headers=real_session.auth_header
    )
    second = await client.post(
        "/v1/favorites", json={"poi_id": poi_id}, headers=real_session.auth_header
    )
    assert first.status_code == 201
    assert second.status_code == 201

    list_response = await client.get("/v1/favorites", headers=real_session.auth_header)
    matches = [f for f in list_response.json()["data"] if f["poi_id"] == poi_id]
    assert len(matches) == 1


async def test_favoriting_a_nonexistent_poi_returns_404(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.post(
        "/v1/favorites",
        json={"poi_id": str(uuid.uuid4())},
        headers=real_session.auth_header,
    )
    assert response.status_code == 404


async def test_favorites_are_isolated_per_user(
    client: AsyncClient, real_session: _RealSession
) -> None:
    poi_id = await _real_poi_id(client, real_session.auth_header)
    await client.post("/v1/favorites", json={"poi_id": poi_id}, headers=real_session.auth_header)

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "b")
        try:
            other_list = await client.get("/v1/favorites", headers=other.auth_header)
            assert poi_id not in {f["poi_id"] for f in other_list.json()["data"]}
        finally:
            await _delete_user(http, other.user_id)


# ---------------------------------------------------------------------------
# F13 — Collections lifecycle, real database
# ---------------------------------------------------------------------------
async def test_create_collection_add_item_and_list(
    client: AsyncClient, real_session: _RealSession
) -> None:
    poi_id = await _real_poi_id(client, real_session.auth_header)

    create_response = await client.post(
        "/v1/collections", json={"name": "Heritage Wishlist"}, headers=real_session.auth_header
    )
    assert create_response.status_code == 201
    collection = create_response.json()["data"]
    assert collection["name"] == "Heritage Wishlist"
    assert collection["item_count"] == 0
    collection_id = collection["id"]

    add_item_response = await client.post(
        f"/v1/collections/{collection_id}/items",
        json={"poi_id": poi_id},
        headers=real_session.auth_header,
    )
    assert add_item_response.status_code == 201
    items = add_item_response.json()["data"]
    assert any(i["poi_id"] == poi_id for i in items)

    get_items_response = await client.get(
        f"/v1/collections/{collection_id}/items", headers=real_session.auth_header
    )
    assert get_items_response.status_code == 200
    assert any(i["poi_id"] == poi_id for i in get_items_response.json()["data"])

    list_response = await client.get("/v1/collections", headers=real_session.auth_header)
    listed = next(c for c in list_response.json()["data"] if c["id"] == collection_id)
    assert listed["item_count"] == 1


async def test_adding_item_to_nonexistent_collection_returns_404(
    client: AsyncClient, real_session: _RealSession
) -> None:
    poi_id = await _real_poi_id(client, real_session.auth_header)
    response = await client.post(
        f"/v1/collections/{uuid.uuid4()}/items",
        json={"poi_id": poi_id},
        headers=real_session.auth_header,
    )
    assert response.status_code == 404


async def test_another_user_cannot_add_items_to_someone_elses_collection(
    client: AsyncClient, real_session: _RealSession
) -> None:
    poi_id = await _real_poi_id(client, real_session.auth_header)
    create_response = await client.post(
        "/v1/collections", json={"name": "Private"}, headers=real_session.auth_header
    )
    collection_id = create_response.json()["data"]["id"]

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "c")
        try:
            response = await client.post(
                f"/v1/collections/{collection_id}/items",
                json={"poi_id": poi_id},
                headers=other.auth_header,
            )
            assert response.status_code == 404

            get_response = await client.get(
                f"/v1/collections/{collection_id}/items", headers=other.auth_header
            )
            assert get_response.status_code == 404
        finally:
            await _delete_user(http, other.user_id)
