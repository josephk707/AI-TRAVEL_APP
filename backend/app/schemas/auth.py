"""
Response schemas for /v1/auth/* — see docs/API_SPECIFICATION.md §2.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

# Matches the CHECK constraint in migration 20260828120002_add_preferred_language.sql
# exactly — this Literal is the single source of truth for request validation;
# the DB constraint is the defense-in-depth backstop, not the primary check.
SupportedLanguage = Literal["en", "hi", "te", "ml", "kn", "ta"]


class ProfileResponse(BaseModel):
    id: UUID
    display_name: str | None
    avatar_url: str | None
    home_region: str | None
    travel_style: str | None
    pace: str | None
    budget_bracket: str | None
    travel_companion: str | None
    trip_motivation: str | None
    role: str
    preferred_language: str
    onboarding_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UpdateProfileRequest(BaseModel):
    """PATCH /v1/auth/me — currently scoped to just the one field this
    phase actually needs (language preference). Not a general profile-edit
    endpoint yet; extend deliberately, not by loosening this model."""

    preferred_language: SupportedLanguage


class BootstrapResponse(BaseModel):
    profile: ProfileResponse
    # True only on the defensive-creation fallback path (ProfilesRepository
    # .create_if_missing actually had to insert). False on every normal
    # bootstrap call, since the on_auth_user_created trigger already
    # created the row before this endpoint could ever be reached.
    created: bool


class LogoutResponse(BaseModel):
    status: str
