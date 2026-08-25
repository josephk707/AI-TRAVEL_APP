"""
/v1/onboarding/* — see docs/API_SPECIFICATION.md §3 for the full contract.

Every route here requires a real, cryptographically verified Supabase
access token (via app.api.deps.get_current_user) — identity always comes
from the verified token, never a client-supplied id.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Response, status

from app.api.deps import get_current_user
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope, Meta
from app.schemas.onboarding import (
    InterestResponse,
    OnboardingResponseData,
    OnboardingResponsesRequest,
    OnboardingStatusResponse,
)
from app.services import onboarding_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/interests", response_model=Envelope[list[InterestResponse]])
async def get_interests(
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[list[InterestResponse]]:
    """Curated interest tags for the onboarding selection UI. Authenticated
    (not public) — matches every other /v1 endpoint's Bearer requirement in
    API_SPECIFICATION.md §1; the caller identity isn't used for scoping
    since this is shared reference data, not user data."""
    del user
    interests = await onboarding_service.list_interests()
    return Envelope(data=interests)


@router.post("/responses", response_model=Envelope[OnboardingResponseData])
async def submit_responses(
    payload: OnboardingResponsesRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[OnboardingResponseData]:
    """Save-failure never blocks the caller (FR-003 exception flow): on
    failure this returns 202 (schedules exactly one background retry)
    instead of a hard error; FastAPI's default 200 applies on success."""
    data, saved = await onboarding_service.submit_responses(user, payload)

    if not saved:
        response.status_code = status.HTTP_202_ACCEPTED
        background_tasks.add_task(onboarding_service.retry_save_in_background, user.id, payload)

    return Envelope(data=data, meta=Meta(saved=saved))


@router.get("/status", response_model=Envelope[OnboardingStatusResponse])
async def get_status(
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[OnboardingStatusResponse]:
    status_data = await onboarding_service.get_status(user)
    return Envelope(data=status_data)
