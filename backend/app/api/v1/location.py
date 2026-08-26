"""/v1/trips/{id}/location/*, /nearby — F7 (API_SPECIFICATION.md §6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope
from app.schemas.location import (
    LocationConsentRequest,
    LocationPingRequest,
    LocationPingResponse,
    ManualLocationRequest,
)
from app.services import location_service

router = APIRouter(prefix="/trips/{trip_id}", tags=["location"])


@router.post("/location/consent", status_code=200)
async def set_location_consent(
    trip_id: str, body: LocationConsentRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[dict]:
    await location_service.set_consent(trip_id, user.id, body.consent)
    return Envelope(data={"consent": body.consent})


@router.post("/location/ping", response_model=Envelope[LocationPingResponse])
async def submit_location_ping(
    trip_id: str, body: LocationPingRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[LocationPingResponse]:
    result = await location_service.submit_ping(trip_id, user.id, body.lat, body.lng)
    return Envelope(data=LocationPingResponse.model_validate(result))


@router.post("/location/manual", response_model=Envelope[LocationPingResponse])
async def submit_manual_location(
    trip_id: str, body: ManualLocationRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[LocationPingResponse]:
    result = await location_service.submit_manual_location(trip_id, user.id, body.poi_id)
    return Envelope(data=LocationPingResponse.model_validate(result))


@router.get("/nearby", response_model=Envelope[list[dict]])
async def get_nearby(
    trip_id: str, lat: float, lng: float, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[list[dict]]:
    results = await location_service.get_nearby(trip_id, user.id, lat, lng)
    return Envelope(data=results)
