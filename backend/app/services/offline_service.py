"""
F26 — Offline Heritage Access (IMPLEMENTATION_BLUEPRINT.md F26). Packages
the trip's real itinerary POIs, their real published heritage overview
content, and the destination's real curated phrasebook entries into one
response the mobile client persists locally (`expo-file-system`) —
pre-generated content only, no on-device inference, matching the
Blueprint's own "AI component: None" row for this feature.

**Documented scope decision:** map-tile offline caching (also referenced
by `MOBILE_ARCHITECTURE.md`'s "local content + map tile cache" line) is
NOT implemented — `react-native-maps` has no first-party, verifiable
offline-tile API this project could build against without an unproven,
device-only native module; heritage narration + phrasebook + the trip's
own itinerary list (which the mobile client already caches for
`ItineraryViewScreen`) is the real, working, verifiable offline surface
this phase delivers.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.exceptions import ForbiddenError, NotFoundError
from app.repositories.heritage_repository import HeritageRepository
from app.repositories.phrasebook_repository import PhrasebookRepository
from app.repositories.trips_repository import TripsRepository


async def get_offline_package(trip_id: str, user_id: str) -> dict:
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")

    days = await trips_repo.get_itinerary(trip_id)
    seen_poi_ids: set[str] = set()
    pois: list[dict] = []
    for day in days:
        for item in day["items"]:
            if item["poi_id"] is None:
                continue
            poi_id = str(item["poi_id"])
            if poi_id in seen_poi_ids:
                continue
            seen_poi_ids.add(poi_id)
            pois.append(
                {
                    "poi_id": poi_id,
                    "name": item["poi_name"],
                    "category": item["poi_category"],
                    "lat": item["poi_lat"],
                    "lng": item["poi_lng"],
                }
            )

    heritage_repo = HeritageRepository()
    heritage_content: list[dict] = []
    for poi_id in seen_poi_ids:
        sections = await heritage_repo.get_published_content(poi_id, layer="overview")
        for section in sections:
            heritage_content.append(
                {
                    "poi_id": poi_id,
                    "section_title": section["section_title"],
                    "body_text": section["body_text"],
                    "source_citation": section["source_citation"],
                }
            )

    city_token = trip["destination"].split(",")[0].strip()
    phrasebook_entries = await PhrasebookRepository().list_for_region(city_token)

    return {
        "trip_id": trip_id,
        "packaged_at": datetime.now(UTC),
        "pois": pois,
        "heritage_content": heritage_content,
        "phrasebook_entries": [dict(e, id=str(e["id"])) for e in phrasebook_entries],
    }
