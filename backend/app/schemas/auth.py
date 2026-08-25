"""
Response schemas for /v1/auth/* — see docs/API_SPECIFICATION.md §2.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProfileResponse(BaseModel):
    id: UUID
    display_name: str | None
    avatar_url: str | None
    home_region: str | None
    travel_style: str | None
    pace: str | None
    budget_bracket: str | None
    role: str
    onboarding_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BootstrapResponse(BaseModel):
    profile: ProfileResponse
    # True only on the defensive-creation fallback path (ProfilesRepository
    # .create_if_missing actually had to insert). False on every normal
    # bootstrap call, since the on_auth_user_created trigger already
    # created the row before this endpoint could ever be reached.
    created: bool


class LogoutResponse(BaseModel):
    status: str
