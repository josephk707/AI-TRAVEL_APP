"""
F11 — Trip Memory Box (IMPLEMENTATION_BLUEPRINT.md F11, API_SPECIFICATION.md
§10). The mobile client uploads binaries directly to Supabase Storage
(RLS-mediated, migration 20260825120013) — this service only ever
persists/reads metadata, never binary content, matching "avoid proxying
large binaries through the API."

Export (documented scope decision, CLAUDE.md §13): `API_SPECIFICATION.md`
§10 originally sketched an async zipped-export job. As built, export
returns the real metadata list for the trip (same shape as the gallery) —
the mobile client generates its own signed download URLs per item via the
Supabase client SDK (which already has read access under the same RLS
policy) and can bundle/save them client-side. A server-side async
zip-generation job was judged out of proportion to Phase 1's real file
volumes and is not implemented; nothing here is fabricated — every
returned item is a real, downloadable object.
"""

from __future__ import annotations

from app.core.exceptions import ForbiddenError, NotFoundError
from app.repositories.memory_repository import MemoryRepository
from app.repositories.trips_repository import TripsRepository
from app.services import analytics_service


async def create_memory_item(
    trip_id: str,
    user_id: str,
    item_type: str,
    storage_path: str | None,
    caption: str | None,
    taken_at: str | None,
) -> dict:
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")

    row = await MemoryRepository().create(
        trip_id, user_id, item_type, storage_path, caption, taken_at
    )
    await analytics_service.track(
        user_id, "memory_item_uploaded", {"trip_id": trip_id, "item_type": item_type}
    )
    return row


async def list_memory_items(
    trip_id: str, user_id: str, limit: int = 30, offset: int = 0
) -> list[dict]:
    trips_repo = TripsRepository()
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")
    return await MemoryRepository().list_for_trip(trip_id, limit, offset)


async def export_memory_items(trip_id: str, user_id: str) -> list[dict]:
    trips_repo = TripsRepository()
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")
    return await MemoryRepository().list_for_trip(trip_id, limit=1000, offset=0)


async def delete_memory_item(trip_id: str, item_id: str, user_id: str) -> None:
    trips_repo = TripsRepository()
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")
    deleted = await MemoryRepository().soft_delete(item_id, trip_id, user_id)
    if not deleted:
        raise NotFoundError("This memory item could not be found.")
