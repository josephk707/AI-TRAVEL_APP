"""
Real Expo Push Notification service client — F16 (MOBILE_ARCHITECTURE.md
§7, API_SPECIFICATION.md §15). The only place this codebase calls Expo's
push API, mirroring `google_places_client.py`'s pattern: one typed failure
mode, never a raw httpx exception escaping to a caller.

Expo's push service delivers to FCM/APNs under the hood — this backend
never talks to FCM/APNs directly (IMPLEMENTATION_BLUEPRINT.md §1.2).
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("app.expo_push")

_PUSH_URL = "https://exp.host/--/api/v2/push/send"
_DEFAULT_TIMEOUT_SECONDS = 10.0


class PushDeliveryError(Exception):
    """Raised only for a transport-level failure (network/timeout/non-2xx).
    A per-token delivery receipt error (e.g. DeviceNotRegistered) is NOT
    raised — it's returned in the result list so the caller can decide
    whether to prune that token, per F16's "queue + retry, never block the
    primary action" error-handling requirement."""


async def send_push_notifications(
    tokens: list[str], title: str, body: str, data: dict | None = None
) -> list[dict]:
    """Returns Expo's per-message receipts (each `{"status": "ok"|"error", ...}`).
    An empty token list is a no-op, not an error — always allowed, since a
    user with no registered device is a normal state (F16 §24: in-app
    notifications centre is the guaranteed fallback channel regardless)."""
    if not tokens:
        return []

    messages = [{"to": token, "title": title, "body": body, "data": data or {}} for token in tokens]
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _PUSH_URL,
                json=messages,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
    except httpx.TimeoutException as exc:
        raise PushDeliveryError("Expo push request timed out.") from exc
    except httpx.HTTPError as exc:
        raise PushDeliveryError("Expo push request failed.") from exc

    if response.status_code != 200:
        logger.warning("expo_push_non_200", extra={"status": response.status_code})
        raise PushDeliveryError(f"Expo push service returned HTTP {response.status_code}.")

    try:
        payload = response.json()
    except ValueError as exc:
        raise PushDeliveryError("Expo push service returned a malformed response.") from exc

    data_list = payload.get("data", [])
    if not isinstance(data_list, list):
        raise PushDeliveryError("Expo push service response had an unexpected shape.")
    return data_list
