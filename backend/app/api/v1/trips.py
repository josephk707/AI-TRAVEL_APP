"""
/v1/trips/* — F3/F4/F5/F12 (docs/API_SPECIFICATION.md §4).

Every route requires a verified Supabase access token and scopes access
via `TripsRepository.is_trip_accessible`/`is_trip_owner` — never a
client-supplied user id (CLAUDE.md §5/§7).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.rate_limit import ai_rate_limit
from app.core.security import AuthenticatedUser
from app.repositories.trips_repository import TripsRepository
from app.schemas.common import Envelope, Meta
from app.schemas.trips import (
    ItineraryGenerateRequest,
    ItineraryGenerateResponse,
    ItineraryItemResponse,
    ItineraryItemUpdateRequest,
    ItineraryModifyRequest,
    ItineraryModifyResponse,
    TripCreateRequest,
    TripNoteCreateRequest,
    TripNoteResponse,
    TripResponse,
    TripUpdateRequest,
)
from app.services import idea_extraction_service, itinerary_service, modification_service

router = APIRouter(prefix="/trips", tags=["trips"])


def _day_to_response(day: dict) -> dict:
    return {
        "day_number": day["day_number"],
        "date": day["date"],
        "items": [ItineraryItemResponse.model_validate(_item_to_response(i)) for i in day["items"]],
    }


def _format_time(value: object) -> str | None:
    """asyncpg returns Postgres `time` columns as `datetime.time` objects
    (`str()` on one yields "06:00:00", not the "HH:MM" this API documents)
    — a plain string (e.g. freshly computed by business_rules, not yet
    round-tripped through the database) is passed through as-is."""
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    return str(value)


def _item_to_response(item: dict) -> dict:
    row = dict(item)
    row["id"] = str(row["id"])
    row["poi_id"] = str(row["poi_id"]) if row.get("poi_id") else None
    row["planned_start"] = _format_time(row.get("planned_start"))
    row["planned_end"] = _format_time(row.get("planned_end"))
    return row


def _trip_to_response(trip: dict) -> dict:
    row = dict(trip)
    row["id"] = str(row["id"])
    row["owner_id"] = str(row["owner_id"])
    return row


@router.post("", response_model=Envelope[TripResponse], status_code=201)
async def create_trip(
    body: TripCreateRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[TripResponse]:
    trip = await TripsRepository().create_trip(user.id, **body.model_dump())
    return Envelope(data=TripResponse.model_validate(_trip_to_response(trip)))


@router.get("", response_model=Envelope[list[TripResponse]])
async def list_trips(
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[list[TripResponse]]:
    trips = await TripsRepository().list_trips(user.id)
    return Envelope(data=[TripResponse.model_validate(_trip_to_response(t)) for t in trips])


@router.get("/{trip_id}", response_model=Envelope[TripResponse])
async def get_trip(
    trip_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[TripResponse]:
    repo = TripsRepository()
    trip = await repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await repo.is_trip_accessible(trip_id, user.id):
        raise ForbiddenError("You do not have access to this trip.")
    return Envelope(data=TripResponse.model_validate(_trip_to_response(trip)))


@router.patch("/{trip_id}", response_model=Envelope[TripResponse])
async def update_trip(
    trip_id: str, body: TripUpdateRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[TripResponse]:
    repo = TripsRepository()
    if not await repo.is_trip_owner(trip_id, user.id):
        raise ForbiddenError("Only the trip owner can update this trip.")
    updated = await repo.update_trip(trip_id, **body.model_dump(exclude_none=True))
    if updated is None:
        raise NotFoundError("This trip could not be found.")
    return Envelope(data=TripResponse.model_validate(_trip_to_response(updated)))


@router.delete("/{trip_id}", status_code=204)
async def delete_trip(trip_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> None:
    repo = TripsRepository()
    if not await repo.is_trip_owner(trip_id, user.id):
        raise ForbiddenError("Only the trip owner can delete this trip.")
    await repo.soft_delete_trip(trip_id)


@router.post("/{trip_id}/notes", response_model=Envelope[TripNoteResponse], status_code=201)
async def submit_trip_notes(
    trip_id: str, body: TripNoteCreateRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[TripNoteResponse]:
    """F4 — Idea Extraction. Runs synchronously so the client can show
    extracted places immediately; the raw note is always persisted first,
    before any AI call, so it's never lost even if extraction fails."""
    note, conflicts = await idea_extraction_service.extract_ideas(trip_id, user.id, body.raw_text)
    payload = dict(note)
    payload["id"] = str(payload["id"])
    payload["trip_id"] = str(payload["trip_id"])
    payload["conflicts"] = conflicts
    return Envelope(data=TripNoteResponse.model_validate(payload))


@router.get("/{trip_id}/notes", response_model=Envelope[list[TripNoteResponse]])
async def list_trip_notes(
    trip_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[list[TripNoteResponse]]:
    repo = TripsRepository()
    if not await repo.is_trip_accessible(trip_id, user.id):
        raise ForbiddenError("You do not have access to this trip.")
    notes = await repo.list_notes(trip_id)
    payload = []
    for note in notes:
        row = dict(note)
        row["id"] = str(row["id"])
        row["trip_id"] = str(row["trip_id"])
        row["conflicts"] = []
        payload.append(row)
    return Envelope(data=[TripNoteResponse.model_validate(p) for p in payload])


@router.post("/{trip_id}/itinerary/generate", response_model=Envelope[ItineraryGenerateResponse])
async def generate_itinerary(
    trip_id: str,
    body: ItineraryGenerateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    _rl: None = Depends(ai_rate_limit),
) -> Envelope[ItineraryGenerateResponse]:
    result, degraded = await itinerary_service.generate_itinerary(trip_id, user.id, body)
    result["days"] = [_day_to_response(d) for d in result["days"]]
    meta = (
        Meta(
            degraded_mode=True,
            message="Live generation is temporarily unavailable — showing a curated starter plan.",
        )
        if degraded
        else None
    )
    return Envelope(data=ItineraryGenerateResponse.model_validate(result), meta=meta)


@router.post("/{trip_id}/itinerary/modify", response_model=Envelope[ItineraryModifyResponse])
async def modify_itinerary(
    trip_id: str,
    body: ItineraryModifyRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    _rl: None = Depends(ai_rate_limit),
) -> Envelope[ItineraryModifyResponse]:
    result = await modification_service.modify_itinerary(trip_id, user.id, body.message)
    result["days"] = [_day_to_response(d) for d in result["days"]]
    return Envelope(data=ItineraryModifyResponse.model_validate(result))


@router.get("/{trip_id}/itinerary", response_model=Envelope[list[dict]])
async def get_itinerary(
    trip_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope:
    repo = TripsRepository()
    if not await repo.is_trip_accessible(trip_id, user.id):
        raise ForbiddenError("You do not have access to this trip.")
    days = await repo.get_itinerary(trip_id)
    return Envelope(data=[_day_to_response(d) for d in days])


@router.patch(
    "/{trip_id}/itinerary/items/{item_id}", response_model=Envelope[ItineraryItemResponse]
)
async def update_itinerary_item(
    trip_id: str,
    item_id: str,
    body: ItineraryItemUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[ItineraryItemResponse]:
    repo = TripsRepository()
    if not await repo.is_trip_accessible(trip_id, user.id):
        raise ForbiddenError("You do not have access to this trip.")
    fields = body.model_dump(exclude_none=True)
    if "planned_start" in fields or "estimated_duration_min" in fields:
        current = await repo.get_item(item_id, trip_id)
        if current is None:
            raise NotFoundError("This itinerary item could not be found.")
        from app.services import business_rules

        planned_start = fields.get("planned_start", current.get("planned_start"))
        duration = fields.get("estimated_duration_min", current.get("estimated_duration_min"))
        fields["planned_end"] = business_rules.compute_planned_end(planned_start, duration)
    updated = await repo.update_item(item_id, trip_id, **fields)
    if updated is None:
        raise NotFoundError("This itinerary item could not be found.")
    return Envelope(data=ItineraryItemResponse.model_validate(_item_to_response(updated)))
