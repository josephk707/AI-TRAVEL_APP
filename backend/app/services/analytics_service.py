"""
F18 — Analytics (Internal) (IMPLEMENTATION_BLUEPRINT.md F18,
DATABASE_SCHEMA.md §12). `track()` is the one function every feature calls
to instrument a funnel step — always fire-and-forget: an analytics
failure must never break the user-facing action it's instrumenting
(F18's own documented error handling), so every exception is caught and
logged, never re-raised.
"""

from __future__ import annotations

import logging
from typing import Any

from app.repositories.analytics_repository import AnalyticsRepository

logger = logging.getLogger("app.analytics")


async def track(
    user_id: str | None, event_name: str, properties: dict[str, Any] | None = None
) -> None:
    try:
        await AnalyticsRepository().record(user_id, event_name, properties)
    except Exception:  # noqa: BLE001 - analytics must never break the primary flow
        logger.warning("analytics_event_failed", extra={"event_name": event_name}, exc_info=True)


async def get_kpis() -> dict[str, int]:
    repo = AnalyticsRepository()
    return {
        "itineraries_generated": await repo.count_event("itinerary_generated"),
        "trips_started": await repo.count_event("trip_started"),
        "trips_completed": await repo.count_event("trip_completed"),
        "memory_items_uploaded": await repo.count_event("memory_item_uploaded"),
        "reviews_submitted": await repo.count_event("review_submitted"),
        "favorites_added": await repo.count_event("favorite_added"),
        "feedback_submitted": await repo.count_event("feedback_submitted"),
    }
