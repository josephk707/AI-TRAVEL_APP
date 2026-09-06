"""
F20 — Dynamic Itinerary Re-Adaptation Engine (IMPLEMENTATION_BLUEPRINT.md
F20, AI_ARCHITECTURE.md §8). Only the `weather` trigger type is genuinely
auto-detected this phase — it is the one signal this codebase already has
a real, live external data source for (`weather_service.check_adverse_weather`,
built for F3's H7 rule). `closure`/`delay`/`off_route`/`missed_activity`/
`budget_overrun`/`schedule_change` remain valid `disruption_events.trigger_type`
values the schema and this service's `resolve()` path fully support, but
none of those has a real, live signal source available anywhere in this
codebase (no transit-delay feed, no live POI-closure feed beyond what
Google Places already returns at search time) — documented scope
decision, not a silent gap (PHASE_STATUS.md Phase 8). `manual_request` IS
real: the traveller-facing "check now" action in `OnTripCompanionScreen`.

**Documented decision (no scheduling infrastructure exists yet in this
environment — same class of gap as the still-unbuilt `location_pings`
retention job, DATABASE_SCHEMA.md §9):** rather than a real `pg_cron` job
this environment cannot deploy or verify, checks run opportunistically
from the existing F7 location-ping flow (already client-throttled to
~60s/50m) and from an explicit manual trigger — both real, both
observable, matching §21.2's "not an app that interrupts constantly"
intent without inventing unverifiable infra.

Step order matches AI_ARCHITECTURE.md §8 exactly: re-evaluate only
remaining items, generate 2-3 real alternatives (never a single forced
choice), attach a plain-language reason, write `disruption_events` with
status='proposed' — nothing is EVER applied to `itinerary_items` until
the traveller explicitly accepts via `resolve()`.
"""

from __future__ import annotations

import uuid

from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from app.repositories.disruption_repository import DisruptionRepository
from app.repositories.pois_repository import PoisRepository
from app.repositories.trips_repository import TripsRepository
from app.services import weather_service

_ALTERNATIVE_RADIUS_M = 3000.0
_MAX_ALTERNATIVES = 3


async def _find_alternatives(
    lat: float, lng: float, category: str | None, exclude_poi_id: str
) -> list[dict]:
    candidates = await PoisRepository().search_nearby(
        lat, lng, _ALTERNATIVE_RADIUS_M, category=category, limit=_MAX_ALTERNATIVES + 1
    )
    alternatives = [c for c in candidates if str(c["id"]) != exclude_poi_id]
    return [
        {"poi_id": str(c["id"]), "poi_name": c["name"], "lat": c["lat"], "lng": c["lng"]}
        for c in alternatives[:_MAX_ALTERNATIVES]
    ]


async def check_for_disruptions(trip_id: str) -> list[dict]:
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        return []

    days = await trips_repo.get_itinerary(trip_id)
    disruption_repo = DisruptionRepository()
    created: list[dict] = []

    for day in days:
        if day["date"] is None:
            continue
        for item in day["items"]:
            if item["status"] not in ("planned", "confirmed"):
                continue
            if item["poi_lat"] is None or item["poi_lng"] is None:
                continue
            item_id = str(item["id"])
            if await disruption_repo.has_open_proposal_for_item(item_id):
                continue

            adverse = await weather_service.check_adverse_weather(
                item["poi_lat"], item["poi_lng"], day["date"].isoformat()
            )
            if not adverse:
                continue

            alternatives = await _find_alternatives(
                item["poi_lat"],
                item["poi_lng"],
                item["poi_category"],
                str(item["poi_id"]) if item.get("poi_id") else "",
            )
            reason = (
                f"Adverse weather is forecast for {item['poi_name']} on {day['date'].isoformat()}."
            )
            if not alternatives:
                reason += (
                    " No comparable nearby alternative was found — "
                    "you may want to plan around this."
                )

            event = await disruption_repo.create(
                trip_id,
                item_id,
                "weather",
                {"reason": reason, "alternatives": alternatives},
            )
            created.append(event)

    return created


async def list_disruptions(trip_id: str, user_id: str) -> list[dict]:
    trips_repo = TripsRepository()
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")
    return await DisruptionRepository().list_for_trip(trip_id)


async def resolve_disruption(
    trip_id: str, event_id: str, user_id: str, decision: str, alternative_index: int | None
) -> dict:
    trips_repo = TripsRepository()
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")

    disruption_repo = DisruptionRepository()
    event = await disruption_repo.get(event_id, trip_id)
    if event is None:
        raise NotFoundError("This disruption event could not be found.")
    if event["status"] != "proposed":
        raise ConflictError("This disruption has already been resolved.")

    if decision == "dismiss":
        updated = await disruption_repo.resolve(event_id, trip_id, "dismissed")
        assert updated is not None
        return updated

    alternatives = event["proposal"].get("alternatives", [])
    if not alternatives:
        raise AppError(
            "NO_ALTERNATIVE_AVAILABLE",
            "There is no alternative to accept for this disruption.",
            422,
        )
    if alternative_index is None or not (0 <= alternative_index < len(alternatives)):
        raise AppError(
            "INVALID_ALTERNATIVE_INDEX",
            "Choose one of the proposed alternatives.",
            400,
        )

    chosen = alternatives[alternative_index]
    await trips_repo.update_item(
        str(event["itinerary_item_id"]),
        trip_id,
        poi_id=uuid.UUID(chosen["poi_id"]),
        weather_flag=True,
        weather_alternative_suggestion=event["proposal"].get("reason"),
    )
    updated = await disruption_repo.resolve(event_id, trip_id, "accepted")
    assert updated is not None
    return updated
