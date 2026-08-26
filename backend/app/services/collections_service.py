"""
F13 — Collections & Favourites (IMPLEMENTATION_BLUEPRINT.md F13,
API_SPECIFICATION.md §11).

Favouriting/collecting is an explicit personalization signal
(AI_ARCHITECTURE.md §20/§7) — logged as a real `feedback_signals` row,
not merely stored as a UI preference, so the Personalization Engine can
read it back.
"""

from __future__ import annotations

from typing import Any

from app.core.exceptions import NotFoundError
from app.repositories.ai_conversations_repository import FeedbackRepository
from app.repositories.collections_repository import CollectionsRepository
from app.repositories.pois_repository import PoisRepository
from app.services import analytics_service


async def add_favorite(user_id: str, poi_id: str) -> None:
    poi = await PoisRepository().get_by_id(poi_id)
    if poi is None:
        raise NotFoundError("This place could not be found.")
    repo = CollectionsRepository()
    if not await repo.is_favorite(user_id, poi_id):
        await repo.add_favorite(user_id, poi_id)
        await FeedbackRepository().log_signal(
            user_id,
            trip_id=None,
            itinerary_item_id=None,
            signal_type="accept",
            value={"source": "favorite", "poi_id": poi_id},
        )
        await analytics_service.track(user_id, "favorite_added", {"poi_id": poi_id})


async def remove_favorite(user_id: str, poi_id: str) -> None:
    await CollectionsRepository().remove_favorite(user_id, poi_id)


async def list_favorites(user_id: str) -> list[dict[str, Any]]:
    return await CollectionsRepository().list_favorites(user_id)


async def create_collection(user_id: str, name: str) -> dict[str, Any]:
    row = await CollectionsRepository().create_collection(user_id, name)
    row["item_count"] = 0
    return row


async def list_collections(user_id: str) -> list[dict[str, Any]]:
    return await CollectionsRepository().list_collections(user_id)


async def add_item_to_collection(user_id: str, collection_id: str, poi_id: str) -> None:
    repo = CollectionsRepository()
    collection = await repo.get_collection(collection_id, user_id)
    if collection is None:
        raise NotFoundError("This collection could not be found.")
    poi = await PoisRepository().get_by_id(poi_id)
    if poi is None:
        raise NotFoundError("This place could not be found.")
    await repo.add_item(collection_id, poi_id)
    await FeedbackRepository().log_signal(
        user_id,
        trip_id=None,
        itinerary_item_id=None,
        signal_type="accept",
        value={"source": "collection", "collection_id": collection_id, "poi_id": poi_id},
    )


async def list_collection_items(user_id: str, collection_id: str) -> list[dict[str, Any]]:
    repo = CollectionsRepository()
    collection = await repo.get_collection(collection_id, user_id)
    if collection is None:
        raise NotFoundError("This collection could not be found.")
    return await repo.list_items(collection_id)
