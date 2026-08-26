"""
F7 — Real-Time Location Companion & Arrival Notifications
(IMPLEMENTATION_BLUEPRINT.md F7, API_SPECIFICATION.md §6). Every location
write is gated by the trip's own explicit per-trip consent flag (BR-014) —
checked FIRST, before anything else, and refused (403) rather than
silently accepted if consent was never granted.
"""

from __future__ import annotations

import logging

from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.repositories.location_repository import LocationRepository
from app.repositories.pois_repository import PoisRepository
from app.repositories.trips_repository import TripsRepository
from app.services import analytics_service, notification_service

logger = logging.getLogger("app.services.location")

_NEARBY_RADIUS_M = 1500.0
_ARRIVAL_RADIUS_M = 200.0


async def set_consent(trip_id: str, user_id: str, consent: bool) -> None:
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")
    await LocationRepository().set_consent(trip_id, consent)


async def _nearby_recommendations(lat: float, lng: float, exclude_poi_id: str | None) -> list[dict]:
    rows = await PoisRepository().search_nearby(lat, lng, _NEARBY_RADIUS_M, category=None, limit=6)
    results = []
    for row in rows:
        if exclude_poi_id and str(row["id"]) == exclude_poi_id:
            continue
        from app.services.business_rules import haversine_km

        distance_m = haversine_km(lat, lng, row["lat"], row["lng"]) * 1000
        results.append(
            {"poi_id": str(row["id"]), "name": row["name"], "distance_m": round(distance_m)}
        )
    return results[:5]


async def _handle_arrival(trip_id: str, user_id: str, lat: float, lng: float) -> dict | None:
    location_repo = LocationRepository()
    nearby_item = await location_repo.find_nearby_planned_item(trip_id, lat, lng, _ARRIVAL_RADIUS_M)
    if nearby_item is None:
        return None

    trips_repo = TripsRepository()
    await trips_repo.update_item(str(nearby_item["item_id"]), trip_id, status="completed")
    await notification_service.dispatch(
        user_id,
        type_="arrival",
        title="You've arrived!",
        body=f"Welcome to {nearby_item['poi_name']}.",
        trip_id=trip_id,
        payload={"itinerary_item_id": str(nearby_item["item_id"])},
    )
    return {"itinerary_item_id": str(nearby_item["item_id"]), "poi_name": nearby_item["poi_name"]}


async def submit_ping(trip_id: str, user_id: str, lat: float, lng: float) -> dict:
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")

    location_repo = LocationRepository()
    if not await location_repo.get_consent(trip_id):
        raise AppError(
            "LOCATION_CONSENT_REQUIRED",
            "Location sharing has not been enabled for this trip.",
            403,
        )

    await location_repo.record_ping(trip_id, user_id, lat, lng)
    arrival = await _handle_arrival(trip_id, user_id, lat, lng)
    nearby = await _nearby_recommendations(
        lat, lng, arrival["itinerary_item_id"] if arrival else None
    )

    # F20 — opportunistic disruption check on the real, already-throttled
    # ping cadence (no pg_cron infra exists yet to run this on a true
    # schedule — see disruption_service.py's module docstring). Never
    # blocks or fails the ping response itself.
    try:
        from app.services import disruption_service

        await disruption_service.check_for_disruptions(trip_id)
    except Exception:  # noqa: BLE001 - disruption checking must never break a location ping
        logger.warning("disruption_check_failed", extra={"trip_id": trip_id}, exc_info=True)

    return {"arrival_event": arrival, "nearby": nearby}


async def get_nearby(trip_id: str, user_id: str, lat: float, lng: float) -> list[dict]:
    trips_repo = TripsRepository()
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")
    return await _nearby_recommendations(lat, lng, None)


async def submit_manual_location(trip_id: str, user_id: str, poi_id: str) -> dict:
    """FR-006 exception flow: GPS permission denied/unavailable — the
    traveller confirms their location manually instead. Never requires
    location consent (no GPS write occurs at all)."""
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")

    poi = await PoisRepository().get_by_id(poi_id)
    if poi is None:
        raise NotFoundError("This place could not be found.")

    arrival = await _handle_arrival(trip_id, user_id, poi["lat"], poi["lng"])
    await analytics_service.track(
        user_id, "manual_location_confirmed", {"trip_id": trip_id, "poi_id": poi_id}
    )
    return {"arrival_event": arrival, "nearby": []}
