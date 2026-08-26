"""/v1/notifications, /v1/devices/push-token — F16 (API_SPECIFICATION.md §15)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope
from app.schemas.notifications import NotificationResponse, RegisterPushTokenRequest
from app.services import notification_service

router = APIRouter(tags=["notifications"])


def _to_response(row: dict) -> dict:
    return dict(
        row,
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        trip_id=str(row["trip_id"]) if row.get("trip_id") else None,
    )


@router.get("/notifications", response_model=Envelope[list[NotificationResponse]])
async def list_notifications(
    limit: int = 30, offset: int = 0, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[list[NotificationResponse]]:
    rows = await notification_service.list_notifications(user.id, limit, offset)
    return Envelope(data=[NotificationResponse.model_validate(_to_response(r)) for r in rows])


@router.patch(
    "/notifications/{notification_id}/read", response_model=Envelope[NotificationResponse]
)
async def mark_notification_read(
    notification_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[NotificationResponse]:
    row = await notification_service.mark_read(notification_id, user.id)
    if row is None:
        raise NotFoundError("This notification could not be found.")
    return Envelope(data=NotificationResponse.model_validate(_to_response(row)))


@router.post("/devices/push-token", status_code=201)
async def register_push_token(
    body: RegisterPushTokenRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[dict]:
    await notification_service.register_push_token(user.id, body.expo_push_token, body.platform)
    return Envelope(data={"registered": True})


@router.delete("/devices/push-token", status_code=204)
async def unregister_push_token(
    expo_push_token: str, user: AuthenticatedUser = Depends(get_current_user)
) -> None:
    await notification_service.unregister_push_token(user.id, expo_push_token)
