"""
Integration tests for /v1/trips/{id}/memory-items — F11 Trip Memory Box
(IMPLEMENTATION_BLUEPRINT.md F11, API_SPECIFICATION.md §10). Exercised
with REAL Supabase-issued access tokens against the REAL Supabase project
(same technique as test_trips_api.py — not mocked). Binary upload itself
is the mobile client's own direct-to-Storage responsibility (see
memory_service.py's module docstring) — these tests exercise the metadata
layer, using `item_type="note"` (no storage_path required) to stay
independent of that separate upload path.

Run with:
  python scripts/run_live_tests.py tests/test_memory_api.py -v
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
        "Full Supabase configuration not set — memory box API integration "
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
    email = f"memory-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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
async def test_list_memory_items_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.get(f"/v1/trips/{uuid.uuid4()}/memory-items")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# F11 — Memory item lifecycle, real database
# ---------------------------------------------------------------------------
async def test_create_list_and_delete_memory_item(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header)

    create_response = await client.post(
        f"/v1/trips/{trip_id}/memory-items",
        json={"item_type": "note", "caption": "Sunrise at the Taj was unforgettable."},
        headers=real_session.auth_header,
    )
    assert create_response.status_code == 201
    item = create_response.json()["data"]
    assert item["item_type"] == "note"
    assert item["retention_expires_at"]
    item_id = item["id"]

    list_response = await client.get(
        f"/v1/trips/{trip_id}/memory-items", headers=real_session.auth_header
    )
    assert list_response.status_code == 200
    assert any(i["id"] == item_id for i in list_response.json()["data"])

    export_response = await client.get(
        f"/v1/trips/{trip_id}/memory-items/export", headers=real_session.auth_header
    )
    assert export_response.status_code == 200
    assert any(i["id"] == item_id for i in export_response.json()["data"])

    delete_response = await client.delete(
        f"/v1/trips/{trip_id}/memory-items/{item_id}", headers=real_session.auth_header
    )
    assert delete_response.status_code == 204

    list_after = await client.get(
        f"/v1/trips/{trip_id}/memory-items", headers=real_session.auth_header
    )
    assert not any(i["id"] == item_id for i in list_after.json()["data"])


async def test_deleting_someone_elses_memory_item_returns_403(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header)
    create_response = await client.post(
        f"/v1/trips/{trip_id}/memory-items",
        json={"item_type": "note", "caption": "Private memory"},
        headers=real_session.auth_header,
    )
    item_id = create_response.json()["data"]["id"]

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "other")
        try:
            response = await client.delete(
                f"/v1/trips/{trip_id}/memory-items/{item_id}", headers=other.auth_header
            )
            assert response.status_code == 403
        finally:
            await _delete_user(http, other.user_id)


async def test_another_user_cannot_list_someone_elses_memory_items(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header)
    await client.post(
        f"/v1/trips/{trip_id}/memory-items",
        json={"item_type": "note", "caption": "Private memory"},
        headers=real_session.auth_header,
    )

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "other2")
        try:
            response = await client.get(
                f"/v1/trips/{trip_id}/memory-items", headers=other.auth_header
            )
            assert response.status_code == 403
        finally:
            await _delete_user(http, other.user_id)


async def test_memory_item_on_nonexistent_trip_returns_404(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.post(
        f"/v1/trips/{uuid.uuid4()}/memory-items",
        json={"item_type": "note", "caption": "orphaned"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 404
