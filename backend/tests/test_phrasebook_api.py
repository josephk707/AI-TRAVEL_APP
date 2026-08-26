"""
Integration tests for /v1/phrasebook/{region}, /v1/trips/{id}/phrasebook/
download — F10 Local Phrase Assistant, static half (IMPLEMENTATION_BLUEPRINT.md
F10, API_SPECIFICATION.md §9). Exercised against the REAL Supabase project
and the REAL curated content seeded by scripts/seed_phrasebook.py — not
mocked, not fabricated.

Run with:
  python scripts/run_live_tests.py tests/test_phrasebook_api.py -v
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
        "Full Supabase configuration not set — phrasebook API integration "
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
    email = f"phrasebook-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
async def test_get_phrasebook_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.get("/v1/phrasebook/Agra")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# F10 — Real curated content, seeded by scripts/seed_phrasebook.py
# ---------------------------------------------------------------------------
async def test_get_phrasebook_for_a_seeded_region_returns_real_curated_phrases(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get("/v1/phrasebook/Agra", headers=real_session.auth_header)
    assert response.status_code == 200
    entries = response.json()["data"]
    assert entries, "seed_phrasebook.py must have seeded Agra region entries"
    entry = entries[0]
    assert entry["phrase_en"]
    assert entry["phrase_local_script"]
    assert entry["phrase_transliteration"]
    assert entry["language_code"] == "hi-IN"


async def test_get_phrasebook_filters_by_language_and_category(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get(
        "/v1/phrasebook/Agra",
        params={"language": "hi-IN", "category": "courtesy"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 200
    entries = response.json()["data"]
    assert entries
    assert all(e["language_code"] == "hi-IN" for e in entries)
    assert all(e["category"] == "courtesy" for e in entries)


async def test_get_phrasebook_for_an_unseeded_region_returns_empty_not_an_error(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get(
        f"/v1/phrasebook/NoSuchRegion{uuid.uuid4().hex[:6]}", headers=real_session.auth_header
    )
    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_mysore_region_has_kannada_entries(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get("/v1/phrasebook/Mysore", headers=real_session.auth_header)
    assert response.status_code == 200
    entries = response.json()["data"]
    assert entries
    assert any(e["language_code"] == "kn-IN" for e in entries)


async def test_madurai_region_has_tamil_entries(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.get("/v1/phrasebook/Madurai", headers=real_session.auth_header)
    assert response.status_code == 200
    entries = response.json()["data"]
    assert entries
    assert any(e["language_code"] == "ta-IN" for e in entries)


# ---------------------------------------------------------------------------
# F10 — Per-trip download derives the region from the trip's destination
# ---------------------------------------------------------------------------
async def test_download_trip_phrasebook_derives_region_from_destination(
    client: AsyncClient, real_session: _RealSession
) -> None:
    create_response = await client.post(
        "/v1/trips",
        json={"title": "Agra Trip", "destination": "Agra, India"},
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]

    response = await client.post(
        f"/v1/trips/{trip_id}/phrasebook/download", headers=real_session.auth_header
    )
    assert response.status_code == 200
    assert response.json()["data"]


async def test_download_trip_phrasebook_rejects_another_users_trip(
    client: AsyncClient, real_session: _RealSession
) -> None:
    create_response = await client.post(
        "/v1/trips",
        json={"title": "Agra Trip", "destination": "Agra, India"},
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "other")
        try:
            response = await client.post(
                f"/v1/trips/{trip_id}/phrasebook/download", headers=other.auth_header
            )
            assert response.status_code == 403
        finally:
            await _delete_user(http, other.user_id)


async def test_download_phrasebook_for_nonexistent_trip_returns_404(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.post(
        f"/v1/trips/{uuid.uuid4()}/phrasebook/download", headers=real_session.auth_header
    )
    assert response.status_code == 404
