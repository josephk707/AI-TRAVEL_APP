"""/v1/trips/{id}/invite, /v1/trips/invite/{token}/accept,
/v1/trips/{id}/members/*, /v1/trips/{id}/itinerary/reconcile — F19
(API_SPECIFICATION.md §13)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.api.v1.trips import _day_to_response
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope
from app.schemas.group import (
    InviteAcceptResponse,
    InviteCreateRequest,
    InviteResponse,
    MemberPreferencesRequest,
    MemberPreferencesResponse,
    ReconcileResponse,
    TripMemberResponse,
)
from app.services import group_service

router = APIRouter(tags=["group"])


@router.post("/trips/{trip_id}/invite", response_model=Envelope[InviteResponse], status_code=201)
async def create_invite(
    trip_id: str, body: InviteCreateRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[InviteResponse]:
    row = await group_service.create_invite(trip_id, user.id, body.method, body.email)
    return Envelope(
        data=InviteResponse.model_validate(
            dict(row, id=str(row["id"]), trip_id=str(row["trip_id"]))
        )
    )


@router.post("/trips/invite/{invite_token}/accept", response_model=Envelope[InviteAcceptResponse])
async def accept_invite(
    invite_token: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[InviteAcceptResponse]:
    result = await group_service.accept_invite(invite_token, user.id)
    return Envelope(data=InviteAcceptResponse.model_validate(result))


@router.post(
    "/trips/{trip_id}/members/{user_id}/preferences",
    response_model=Envelope[MemberPreferencesResponse],
)
async def submit_preferences(
    trip_id: str,
    user_id: str,
    body: MemberPreferencesRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[MemberPreferencesResponse]:
    row = await group_service.submit_preferences(
        trip_id, user_id, user.id, body.interests, body.budget_max, body.constraints
    )
    return Envelope(
        data=MemberPreferencesResponse.model_validate(
            dict(row, trip_id=str(row["trip_id"]), user_id=str(row["user_id"]))
        )
    )


@router.get("/trips/{trip_id}/members", response_model=Envelope[list[TripMemberResponse]])
async def list_members(
    trip_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[list[TripMemberResponse]]:
    rows = await group_service.list_members(trip_id, user.id)
    payload = [dict(r, trip_id=str(r["trip_id"]), user_id=str(r["user_id"])) for r in rows]
    return Envelope(data=[TripMemberResponse.model_validate(p) for p in payload])


@router.post("/trips/{trip_id}/itinerary/reconcile", response_model=Envelope[ReconcileResponse])
async def reconcile(
    trip_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[ReconcileResponse]:
    result = await group_service.reconcile(trip_id, user.id)
    result["days"] = [_day_to_response(d) for d in result["days"]]
    return Envelope(data=ReconcileResponse.model_validate(result))
