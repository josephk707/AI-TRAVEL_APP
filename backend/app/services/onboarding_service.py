"""
Business logic for /v1/onboarding/* — route handlers
(app/api/v1/onboarding.py) stay thin and delegate here, per CLAUDE.md §7
(Router -> Service -> Repository).
"""

from __future__ import annotations

import asyncio
import logging

from app.core.exceptions import AppError
from app.core.security import AuthenticatedUser
from app.repositories.interests_repository import InterestsRepository
from app.repositories.onboarding_repository import OnboardingRepository
from app.schemas.onboarding import (
    InterestResponse,
    OnboardingResponseData,
    OnboardingResponsesRequest,
    OnboardingStatusResponse,
)

logger = logging.getLogger("app.services.onboarding")

# One retry, after a short delay, if the initial synchronous save fails —
# matches FR-003's exception flow exactly ("the user is not blocked from
# proceeding -- defaults are used and a retry happens silently in the
# background"). Not a general-purpose job queue: a single bounded retry is
# proportionate for this MVP-scale requirement, and the client already has
# an authoritative way to check the real outcome afterward (GET
# /onboarding/status), so an unbounded/queued retry system would be
# over-engineering relative to what FR-003 actually asks for.
_BACKGROUND_RETRY_DELAY_SECONDS = 2.0


async def list_interests() -> list[InterestResponse]:
    rows = await InterestsRepository().list_interests()
    return [InterestResponse.model_validate(row) for row in rows]


async def get_status(user: AuthenticatedUser) -> OnboardingStatusResponse:
    repo = OnboardingRepository()
    state = await repo.get_onboarding_state(user.id)
    completed_at = state["onboarding_completed_at"] if state else None
    return OnboardingStatusResponse(
        onboarding_completed=completed_at is not None,
        onboarding_completed_at=completed_at,  # type: ignore[arg-type]
    )


async def _validate_interest_ids(interest_ids: list[int]) -> None:
    if not interest_ids:
        return
    known = {row["id"] for row in await InterestsRepository().list_interests()}
    unknown = sorted(set(interest_ids) - known)
    if unknown:
        raise AppError(
            "INVALID_INTEREST_IDS",
            "One or more selected interests are not recognized.",
            status_code=400,
            details={"unknown_interest_ids": unknown},
        )


async def _save(user_id: str, payload: OnboardingResponsesRequest) -> dict[str, object]:
    repo = OnboardingRepository()
    return await repo.save_onboarding_responses(
        user_id,
        interest_ids=payload.interest_ids,
        travel_style=payload.travel_style,
        pace=payload.pace,
        budget_bracket=payload.budget_bracket,
        travel_companion=payload.travel_companion,
        trip_motivation=payload.trip_motivation,
    )


async def retry_save_in_background(user_id: str, payload: OnboardingResponsesRequest) -> None:
    await asyncio.sleep(_BACKGROUND_RETRY_DELAY_SECONDS)
    try:
        await _save(user_id, payload)
        logger.info("onboarding_background_retry_succeeded")
    except Exception:  # noqa: BLE001 - background task: log and drop, never crash the process
        logger.exception("onboarding_background_retry_failed")


async def submit_responses(
    user: AuthenticatedUser, payload: OnboardingResponsesRequest
) -> tuple[OnboardingResponseData, bool]:
    """Returns (data, saved). On a save failure, schedules exactly one
    background retry (caller is responsible for actually scheduling the
    coroutine via FastAPI's BackgroundTasks — see the router) and returns
    immediately with saved=False rather than surfacing a hard error, per
    FR-003's exception flow. The caller never blocks on the retry."""
    await _validate_interest_ids(payload.interest_ids)

    try:
        row = await _save(user.id, payload)
    except AppError:
        logger.warning("onboarding_save_failed_scheduling_retry")
        data = OnboardingResponseData(
            onboarding_completed=False,
            onboarding_completed_at=None,
            interest_ids=payload.interest_ids,
            travel_style=payload.travel_style,
            pace=payload.pace,
            budget_bracket=payload.budget_bracket,
            travel_companion=payload.travel_companion,
            trip_motivation=payload.trip_motivation,
        )
        return data, False

    interest_ids = await OnboardingRepository().get_interest_ids_for_profile(user.id)
    data = OnboardingResponseData(
        onboarding_completed=row["onboarding_completed_at"] is not None,
        onboarding_completed_at=row["onboarding_completed_at"],  # type: ignore[arg-type]
        interest_ids=interest_ids,
        travel_style=row["travel_style"],  # type: ignore[arg-type]
        pace=row["pace"],  # type: ignore[arg-type]
        budget_bracket=row["budget_bracket"],  # type: ignore[arg-type]
        travel_companion=row["travel_companion"],  # type: ignore[arg-type]
        trip_motivation=row["trip_motivation"],  # type: ignore[arg-type]
    )
    return data, True
