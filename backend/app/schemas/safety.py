"""Request/response schemas for /v1/safety/*, /v1/trips/{id}/share/*,
/v1/share/{token} — F21 Safety/SOS (API_SPECIFICATION.md §16)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TrustedContactCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=254)


class TrustedContactResponse(BaseModel):
    id: str
    user_id: str
    name: str
    phone: str | None
    email: str | None
    created_at: datetime


class ShareStartResponse(BaseModel):
    id: str
    trip_id: str
    share_token: str
    is_active: bool
    started_at: datetime
    expires_at: datetime
    share_url: str


class PublicShareResponse(BaseModel):
    trip_id: str
    is_active: bool
    expires_at: datetime
    last_known_lat: float | None
    last_known_lng: float | None
    recorded_at: datetime | None


class SosResponse(BaseModel):
    id: str
    triggered_at: datetime
    last_known_lat: float | None
    last_known_lng: float | None
    location_captured_at: datetime | None
    contacts_notified: int
