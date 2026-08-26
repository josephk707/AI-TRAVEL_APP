"""Request/response schemas for /v1/trips/{id}/invite, /v1/trips/invite/*,
/v1/trips/{id}/members/*, /v1/trips/{id}/itinerary/reconcile — F19
Group/Collaborative Trip Planning (API_SPECIFICATION.md §13)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.trips import ItineraryDayResponse

_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class InviteCreateRequest(BaseModel):
    method: Literal["link", "email"]
    email: str | None = Field(default=None, pattern=_EMAIL_PATTERN, max_length=254)


class InviteResponse(BaseModel):
    id: str
    trip_id: str
    method: Literal["link", "email"]
    email: str | None
    token: str
    status: Literal["pending", "accepted", "expired"]
    expires_at: datetime
    invite_url: str


class InviteAcceptResponse(BaseModel):
    trip_id: str
    role: Literal["organiser", "member"]
    joined: bool


class MemberPreferencesRequest(BaseModel):
    interests: list[str] = Field(default_factory=list)
    budget_max: float | None = Field(default=None, gt=0)
    constraints: dict[str, Any] = Field(default_factory=dict)


class MemberPreferencesResponse(BaseModel):
    trip_id: str
    user_id: str
    interests: list[str]
    budget_max: float | None
    constraints: dict[str, Any]
    submitted_at: datetime


class TripMemberResponse(BaseModel):
    trip_id: str
    user_id: str
    display_name: str | None
    role: Literal["organiser", "member"]
    invite_status: Literal["invited", "accepted", "declined", "no_response"]
    invited_at: datetime
    responded_at: datetime | None


class ReconcileConflict(BaseModel):
    field: str
    description: str
    resolution: str


class ReconcileResponse(BaseModel):
    trip_id: str
    generation_status: str
    summary: str
    days: list[ItineraryDayResponse]
    conflicts: list[ReconcileConflict]
    included_member_ids: list[str]
    excluded_member_ids: list[str]
