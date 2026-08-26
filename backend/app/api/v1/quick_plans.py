"""/v1/quick-plans* — F22 (API_SPECIFICATION.md §18)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope
from app.schemas.quick_plan import (
    QuickPlanCreateRequest,
    QuickPlanResponse,
    SaveToCollectionResponse,
)
from app.services import quick_plan_service

router = APIRouter(tags=["quick-plans"])


def _to_response(row: dict) -> dict:
    return dict(row, id=str(row["id"]), user_id=str(row["user_id"]))


@router.post("/quick-plans", response_model=Envelope[QuickPlanResponse], status_code=201)
async def create_quick_plan(
    body: QuickPlanCreateRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[QuickPlanResponse]:
    row = await quick_plan_service.generate_quick_plan(
        user.id, body.time_available_min, body.budget, body.occasion, body.lat, body.lng
    )
    return Envelope(data=QuickPlanResponse.model_validate(_to_response(row)))


@router.post(
    "/quick-plans/{quick_plan_id}/save-to-collection",
    response_model=Envelope[SaveToCollectionResponse],
    status_code=201,
)
async def save_to_collection(
    quick_plan_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[SaveToCollectionResponse]:
    result = await quick_plan_service.save_to_collection(quick_plan_id, user.id)
    return Envelope(data=SaveToCollectionResponse.model_validate(result))
