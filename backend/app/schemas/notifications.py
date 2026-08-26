"""Request/response schemas for /v1/notifications, /v1/devices/* — F16
(API_SPECIFICATION.md §15)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

NotificationType = Literal[
    "arrival", "disruption", "memory_expiry", "sos", "group_invite", "reminder", "system"
]


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    trip_id: str | None
    type: NotificationType
    title: str
    body: str
    payload: dict[str, Any]
    read_at: datetime | None
    delivered_channels: list[str]
    created_at: datetime


class RegisterPushTokenRequest(BaseModel):
    expo_push_token: str = Field(min_length=1, max_length=300)
    platform: Literal["ios", "android"]


class UnregisterPushTokenRequest(BaseModel):
    expo_push_token: str = Field(min_length=1, max_length=300)
