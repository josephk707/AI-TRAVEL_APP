"""
F16 — Notifications (IMPLEMENTATION_BLUEPRINT.md F16, API_SPECIFICATION.md
§15). `dispatch()` is the internal notification-dispatch service other
features call (F7 arrival, F11 memory-expiry, F15 over-budget, F17 —
listed as F16's own dependents in the blueprint) — always writes the
`notifications` row FIRST (the guaranteed in-app fallback channel, §24),
then best-effort attempts push delivery; a push failure never blocks or
reverts the notification itself (F16's own documented error handling).
"""

from __future__ import annotations

import logging
from typing import Any

from app.repositories.notifications_repository import NotificationsRepository, PushTokenRepository
from app.services.expo_push_client import PushDeliveryError, send_push_notifications

logger = logging.getLogger("app.services.notification")


async def dispatch(
    user_id: str,
    *,
    type_: str,
    title: str,
    body: str,
    trip_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    notifications_repo = NotificationsRepository()
    notification = await notifications_repo.create(
        user_id,
        trip_id=trip_id,
        type_=type_,
        title=title,
        body=body,
        payload=payload,
        delivered_channels=["in_app"],
    )

    tokens = await PushTokenRepository().list_tokens_for_user(user_id)
    if tokens:
        try:
            await send_push_notifications(tokens, title, body, {"type": type_, **(payload or {})})
        except PushDeliveryError:
            logger.warning("push_delivery_failed", extra={"user_id": user_id}, exc_info=True)
            # Real, honest degrade: the in-app row already exists (the
            # guaranteed fallback channel) — push simply didn't confirm.
            return notification

    return notification


async def list_notifications(
    user_id: str, limit: int = 30, offset: int = 0
) -> list[dict[str, Any]]:
    return await NotificationsRepository().list_for_user(user_id, limit, offset)


async def mark_read(notification_id: str, user_id: str) -> dict[str, Any] | None:
    return await NotificationsRepository().mark_read(notification_id, user_id)


async def register_push_token(user_id: str, expo_push_token: str, platform: str) -> None:
    await PushTokenRepository().upsert(user_id, expo_push_token, platform)


async def unregister_push_token(user_id: str, expo_push_token: str) -> None:
    await PushTokenRepository().delete(user_id, expo_push_token)
