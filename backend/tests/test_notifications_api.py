"""
Integration tests for /v1/notifications, /v1/devices/push-token — F16
Notifications (IMPLEMENTATION_BLUEPRINT.md F16, API_SPECIFICATION.md §15).
Exercised with REAL Supabase-issued access tokens against the REAL
Supabase project (same technique as test_trips_api.py — not mocked). The
Expo push HTTP boundary itself is monkeypatched (same discipline as
test_google_places_client.py) since a real device token cannot exist in
this environment — the in-app notification row is always real.

Run with:
  python scripts/run_live_tests.py tests/test_notifications_api.py -v
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import AsyncClient

from app.services import expo_push_client, notification_service
from app.services.expo_push_client import PushDeliveryError

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and SUPABASE_URL and SERVICE_ROLE_KEY and ANON_KEY),
    reason=(
        "Full Supabase configuration not set — notifications API integration "
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
    email = f"notif-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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
async def test_list_notifications_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.get("/v1/notifications")
    assert response.status_code == 401


async def test_register_push_token_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/devices/push-token",
        json={"expo_push_token": "ExponentPushToken[x]", "platform": "ios"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# F16 — Push token registration lifecycle, real database
# ---------------------------------------------------------------------------
async def test_register_and_unregister_push_token(
    client: AsyncClient, real_session: _RealSession
) -> None:
    token = f"ExponentPushToken[{uuid.uuid4().hex[:16]}]"
    register_response = await client.post(
        "/v1/devices/push-token",
        json={"expo_push_token": token, "platform": "ios"},
        headers=real_session.auth_header,
    )
    assert register_response.status_code == 201

    # Re-registering the same token (e.g. app relaunch) must not error —
    # ON CONFLICT DO UPDATE, not a duplicate-key failure.
    reregister_response = await client.post(
        "/v1/devices/push-token",
        json={"expo_push_token": token, "platform": "android"},
        headers=real_session.auth_header,
    )
    assert reregister_response.status_code == 201

    unregister_response = await client.delete(
        "/v1/devices/push-token",
        params={"expo_push_token": token},
        headers=real_session.auth_header,
    )
    assert unregister_response.status_code == 204


async def test_invalid_platform_value_is_rejected(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.post(
        "/v1/devices/push-token",
        json={"expo_push_token": "ExponentPushToken[x]", "platform": "windows"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# F16 — Notification dispatch, list, and mark-read, real database.
# dispatch() is exercised directly (it's the internal fan-in point every
# other feature — F7 arrival, F15 over-budget — calls into) with the Expo
# HTTP boundary monkeypatched, proving the DB row is the guaranteed
# fallback channel and that a push failure never blocks it.
# ---------------------------------------------------------------------------
async def test_dispatch_creates_notification_even_when_push_delivery_fails(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = f"ExponentPushToken[{uuid.uuid4().hex[:16]}]"
    await client.post(
        "/v1/devices/push-token",
        json={"expo_push_token": token, "platform": "ios"},
        headers=real_session.auth_header,
    )

    async def _failing_send(*args, **kwargs):
        raise PushDeliveryError("simulated transport failure")

    monkeypatch.setattr(notification_service, "send_push_notifications", _failing_send)

    notification = await notification_service.dispatch(
        real_session.user_id,
        type_="system",
        title="Test notification",
        body="This should persist even though push fails.",
    )
    assert notification["title"] == "Test notification"

    list_response = await client.get("/v1/notifications", headers=real_session.auth_header)
    assert list_response.status_code == 200
    notification_ids = {n["id"] for n in list_response.json()["data"]}
    assert str(notification["id"]) in notification_ids

    mark_read_response = await client.patch(
        f"/v1/notifications/{notification['id']}/read", headers=real_session.auth_header
    )
    assert mark_read_response.status_code == 200
    assert mark_read_response.json()["data"]["read_at"] is not None


async def test_dispatch_attempts_real_push_boundary_when_token_registered(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = f"ExponentPushToken[{uuid.uuid4().hex[:16]}]"
    await client.post(
        "/v1/devices/push-token",
        json={"expo_push_token": token, "platform": "ios"},
        headers=real_session.auth_header,
    )

    calls: list[tuple] = []

    async def _fake_send(tokens, title, body, data=None):
        calls.append((tokens, title, body, data))
        return [{"status": "ok"}]

    monkeypatch.setattr(notification_service, "send_push_notifications", _fake_send)

    await notification_service.dispatch(
        real_session.user_id, type_="arrival", title="You've arrived!", body="Welcome."
    )
    assert len(calls) == 1
    assert token in calls[0][0]


async def test_mark_read_on_someone_elses_notification_returns_404(
    client: AsyncClient, real_session: _RealSession
) -> None:
    notification = await notification_service.dispatch(
        real_session.user_id, type_="system", title="Private", body="For me only."
    )

    async with httpx.AsyncClient(timeout=15) as http:
        other = await _create_real_session(http, "other")
        try:
            response = await client.patch(
                f"/v1/notifications/{notification['id']}/read", headers=other.auth_header
            )
            assert response.status_code == 404
        finally:
            await _delete_user(http, other.user_id)


async def test_expo_push_client_no_tokens_is_a_noop_not_an_error() -> None:
    result = await expo_push_client.send_push_notifications([], "t", "b")
    assert result == []
