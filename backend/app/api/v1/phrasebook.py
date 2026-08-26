"""/v1/phrasebook/*, /v1/trips/{id}/phrasebook/download — F10
(API_SPECIFICATION.md §9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.security import AuthenticatedUser
from app.repositories.phrasebook_repository import PhrasebookRepository
from app.repositories.trips_repository import TripsRepository
from app.schemas.common import Envelope
from app.schemas.phrasebook import PhrasebookEntryResponse

router = APIRouter(tags=["phrasebook"])


def _to_response(row: dict) -> dict:
    return dict(row, id=str(row["id"]))


@router.get("/phrasebook/{region}", response_model=Envelope[list[PhrasebookEntryResponse]])
async def get_phrasebook(
    region: str,
    language: str | None = None,
    category: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[list[PhrasebookEntryResponse]]:
    del user
    rows = await PhrasebookRepository().list_for_region(region, language, category)
    return Envelope(data=[PhrasebookEntryResponse.model_validate(_to_response(r)) for r in rows])


@router.post(
    "/trips/{trip_id}/phrasebook/download", response_model=Envelope[list[PhrasebookEntryResponse]]
)
async def download_trip_phrasebook(
    trip_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[list[PhrasebookEntryResponse]]:
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_accessible(trip_id, user.id):
        raise ForbiddenError("You do not have access to this trip.")

    city_token = trip["destination"].split(",")[0].strip()
    rows = await PhrasebookRepository().list_for_region(city_token)
    return Envelope(data=[PhrasebookEntryResponse.model_validate(_to_response(r)) for r in rows])
