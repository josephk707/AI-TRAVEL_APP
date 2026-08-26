"""/v1/trips/{id}/disruptions* — F20 (see app/schemas/disruption.py's
module docstring for the ARCHITECTURE_REVIEW.md H2 resolution)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.exceptions import ForbiddenError
from app.core.security import AuthenticatedUser
from app.repositories.trips_repository import TripsRepository
from app.schemas.common import Envelope
from app.schemas.disruption import DisruptionEventResponse, DisruptionResolveRequest
from app.services import disruption_service

router = APIRouter(prefix="/trips/{trip_id}", tags=["disruptions"])


def _to_response(row: dict) -> dict:
    return dict(
        row,
        id=str(row["id"]),
        trip_id=str(row["trip_id"]),
        itinerary_item_id=str(row["itinerary_item_id"]),
    )


@router.get("/disruptions", response_model=Envelope[list[DisruptionEventResponse]])
async def list_disruptions(
    trip_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[list[DisruptionEventResponse]]:
    rows = await disruption_service.list_disruptions(trip_id, user.id)
    return Envelope(data=[DisruptionEventResponse.model_validate(_to_response(r)) for r in rows])


@router.post("/disruptions/check", response_model=Envelope[list[DisruptionEventResponse]])
async def check_disruptions(
    trip_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[list[DisruptionEventResponse]]:
    if not await TripsRepository().is_trip_accessible(trip_id, user.id):
        raise ForbiddenError("You do not have access to this trip.")
    rows = await disruption_service.check_for_disruptions(trip_id)
    return Envelope(data=[DisruptionEventResponse.model_validate(_to_response(r)) for r in rows])


@router.post("/disruptions/{event_id}/resolve", response_model=Envelope[DisruptionEventResponse])
async def resolve_disruption(
    trip_id: str,
    event_id: str,
    body: DisruptionResolveRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[DisruptionEventResponse]:
    row = await disruption_service.resolve_disruption(
        trip_id, event_id, user.id, body.decision, body.alternative_index
    )
    return Envelope(data=DisruptionEventResponse.model_validate(_to_response(row)))
