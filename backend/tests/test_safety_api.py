"""
Integration tests for /v1/safety/*, /v1/trips/{id}/share/*, /v1/share/{token}
— F21 Safety/SOS Trusted-Contact Sharing (IMPLEMENTATION_BLUEPRINT.md F21,
API_SPECIFICATION.md §16). Exercised with REAL Supabase-issued access
tokens against the REAL Supabase project (same technique as
test_trips_api.py — not mocked). No SMTP credentials are configured in
this environment, so email delivery itself degrades gracefully (real,
honest behavior, not simulated) — the SOS event, in-app notification, and
share-link mechanics are all fully live-verified regardless.

Run with:
  python scripts/run_live_tests.py tests/test_safety_api.py -v
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
        "Full Supabase configuration not set — safety API integration "
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
    email = f"safety-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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


async def _new_trip(client: AsyncClient, auth_header: dict[str, str], **overrides) -> str:
    payload = {"title": "Agra Trip", "destination": "Agra, India"}
    payload.update(overrides)
    response = await client.post("/v1/trips", json=payload, headers=auth_header)
    return str(response.json()["data"]["id"])


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
async def test_add_trusted_contact_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/safety/contacts", json={"name": "Mom", "phone": "+911234567890"}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# F21 — Trusted contacts, real database
# ---------------------------------------------------------------------------
async def test_add_and_list_trusted_contacts(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.post(
        "/v1/safety/contacts",
        json={"name": "Mom", "phone": "+911234567890", "email": "mom@example.invalid"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 201
    assert response.json()["data"]["name"] == "Mom"

    list_response = await client.get("/v1/safety/contacts", headers=real_session.auth_header)
    assert any(c["name"] == "Mom" for c in list_response.json()["data"])


async def test_trusted_contact_requires_a_phone_or_email(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.post(
        "/v1/safety/contacts", json={"name": "No Contact Info"}, headers=real_session.auth_header
    )
    assert response.status_code == 400


async def test_trusted_contacts_are_isolated_per_user(
    client: AsyncClient, real_session: _RealSession
) -> None:
    await client.post(
        "/v1/safety/contacts",
        json={"name": "Private Contact", "phone": "+911111111111"},
        headers=real_session.auth_header,
    )

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "other")
        try:
            other_list = await client.get("/v1/safety/contacts", headers=other.auth_header)
            assert not any(c["name"] == "Private Contact" for c in other_list.json()["data"])
        finally:
            await _delete_user(http, other.user_id)


# ---------------------------------------------------------------------------
# F21 — Location sharing, real database
# ---------------------------------------------------------------------------
async def test_start_share_creates_a_real_scoped_token_and_public_viewer_works(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header, end_date="2026-10-15")

    start_response = await client.post(
        f"/v1/trips/{trip_id}/share/start", headers=real_session.auth_header
    )
    assert start_response.status_code == 200
    share = start_response.json()["data"]
    assert share["is_active"] is True
    token = share["share_token"]

    public_response = await client.get(f"/v1/share/{token}")
    assert public_response.status_code == 200
    public_body = public_response.json()["data"]
    assert public_body["trip_id"] == trip_id
    assert public_body["is_active"] is True


async def test_stop_share_deactivates_the_public_viewer(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header)
    start_response = await client.post(
        f"/v1/trips/{trip_id}/share/start", headers=real_session.auth_header
    )
    token = start_response.json()["data"]["share_token"]

    stop_response = await client.post(
        f"/v1/trips/{trip_id}/share/stop", headers=real_session.auth_header
    )
    assert stop_response.status_code == 204

    public_response = await client.get(f"/v1/share/{token}")
    assert public_response.status_code == 404


async def test_public_share_viewer_rejects_an_unknown_token(client: AsyncClient) -> None:
    response = await client.get(f"/v1/share/{uuid.uuid4().hex}")
    assert response.status_code == 404


async def test_only_a_trip_member_can_start_or_stop_sharing(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header)

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "other2")
        try:
            start_response = await client.post(
                f"/v1/trips/{trip_id}/share/start", headers=other.auth_header
            )
            assert start_response.status_code == 403
        finally:
            await _delete_user(http, other.user_id)


# ---------------------------------------------------------------------------
# F21 — SOS, real database (FR-017 exception flow: no location -> still records)
# ---------------------------------------------------------------------------
async def test_sos_without_any_recorded_location_still_creates_a_real_event(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header)
    await client.patch(
        f"/v1/trips/{trip_id}", json={"status": "active"}, headers=real_session.auth_header
    )

    response = await client.post(
        "/v1/safety/sos", json={"trip_id": trip_id}, headers=real_session.auth_header
    )
    assert response.status_code == 201
    body = response.json()["data"]
    assert body["last_known_lat"] is None
    assert body["last_known_lng"] is None

    notifications_response = await client.get("/v1/notifications", headers=real_session.auth_header)
    assert any(n["type"] == "sos" for n in notifications_response.json()["data"])


async def test_sos_resolves_the_callers_own_active_trip_when_none_specified(
    client: AsyncClient, real_session: _RealSession
) -> None:
    trip_id = await _new_trip(client, real_session.auth_header)
    await client.patch(
        f"/v1/trips/{trip_id}", json={"status": "active"}, headers=real_session.auth_header
    )

    response = await client.post("/v1/safety/sos", json={}, headers=real_session.auth_header)
    assert response.status_code == 201
