"""
Place grounding — turns a model-proposed place ("Humayun's Tomb",
area "Nizamuddin", approx 28.59, 77.25) into a verified itinerary stop
(AI-first itinerary phase, AI_ARCHITECTURE.md §2 step 3b).

Why this exists: the generation prompt now lets Gemini plan from its own
knowledge of a destination instead of only re-ordering the handful of
`pois` rows we happen to have cached, which is what the product owner
asked for — but CLAUDE.md §8 still forbids trusting a model response
blindly. So every proposed place is resolved, in order of trust:

  1. an existing `pois` row (curated seed or previously cached) whose
     name matches                                    -> location_source = "poi"
  2. Geoapify forward geocoding of "<name>, <area>, <destination>", biased
     to the destination centre, accepted only when the provider reports a
     confident match AND the result lies within `max_km` of the centre;
     the verified place is cached into `pois` (source "places_api") so the
     next trip to the same city finds it in step 1   -> "places_api"
  3. the model's own coordinates, accepted only when they also lie within
     a (wider) radius of the destination centre       -> "ai_estimate"
  4. nothing verifiable                               -> "unresolved"

The client labels steps 3 and 4 honestly ("approximate location" /
"location not verified", verify_on_arrival) rather than presenting them
as confirmed — low-confidence output is visibly flagged (CLAUDE.md §8).

Failure handling: a geocoder outage never fails a plan. The first
provider error trips a per-request breaker so the remaining places skip
straight to step 3 instead of each waiting for a timeout.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import get_settings
from app.repositories.pois_repository import PoisRepository
from app.services.business_rules import haversine_km
from app.services.geoapify_geocoding_client import GeoapifyGeocodingClient
from app.services.google_places_client import PlacesProviderError

logger = logging.getLogger("app.services.place_grounding")

LocationSource = Literal["poi", "places_api", "ai_estimate", "unresolved"]

VALID_CATEGORIES = frozenset(
    {"heritage", "restaurant", "attraction", "nature", "shopping", "other"}
)

# A geocoded/model place further than this from the destination centre is
# treated as a different place with the same name (a "City Palace" in
# another state), not as this trip's stop.
DEFAULT_MAX_KM = 80.0
AI_ESTIMATE_MAX_KM = 150.0
# Geoapify result types that mean "the whole city/region", never a stop.
_AREA_RESULT_TYPES = {"country", "state", "county", "city", "postcode", "district", "suburb"}
_MIN_GEOCODE_CONFIDENCE = 0.5
_MAX_CONCURRENT_GEOCODES = 4


@dataclass(frozen=True)
class ProposedPlace:
    name: str
    area: str | None = None
    category: str | None = None
    lat: float | None = None
    lng: float | None = None


@dataclass
class GroundedPlace:
    name: str
    category: str
    location_source: LocationSource
    poi_id: str | None = None
    area: str | None = None
    lat: float | None = None
    lng: float | None = None
    opening_hours: Any | None = None
    avg_cost: float | None = None

    def as_item_fields(self) -> dict[str, Any]:
        """The keys the itinerary pipelines and TripsRepository expect."""
        return {
            "poi_id": self.poi_id,
            "poi_name": self.name,
            "poi_lat": self.lat,
            "poi_lng": self.lng,
            "poi_category": self.category,
            "poi_opening_hours": self.opening_hours,
            "poi_avg_cost": self.avg_cost,
            "place_name": self.name,
            "place_area": self.area,
            "place_category": self.category,
            "place_lat": self.lat,
            "place_lng": self.lng,
            "location_source": self.location_source,
        }


def normalize_name(value: str) -> str:
    """Case/diacritic/punctuation-insensitive form used for name matching:
    "The Humayun's Tomb" and "humayuns tomb" compare equal."""
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    # Apostrophes vanish ("Humayun's" -> "humayuns"); every other symbol
    # becomes a word break.
    text = re.sub(r"['\u2019`]", "", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    text = re.sub(r"\s+", " ", text).strip()
    if text.startswith("the "):
        text = text[4:]
    return text


def valid_category(value: str | None) -> str:
    return value if value in VALID_CATEGORIES else "other"


def within_km(
    centre: tuple[float, float] | None, lat: float | None, lng: float | None, max_km: float
) -> bool:
    """True when no centre is known (nothing to check against) or the
    point lies within `max_km` of it."""
    if lat is None or lng is None:
        return False
    if centre is None:
        return True
    return haversine_km(centre[0], centre[1], lat, lng) <= max_km


def match_candidate(name: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Exact normalized-name match first, then a containment match either
    way ("Red Fort" vs "Red Fort (Lal Qila)") guarded by a minimum length
    so a short token like "Gate" can't swallow "India Gate"."""
    target = normalize_name(name)
    if not target:
        return None
    for candidate in candidates:
        if normalize_name(str(candidate.get("name", ""))) == target:
            return candidate
    if len(target) < 6:
        return None
    for candidate in candidates:
        cand = normalize_name(str(candidate.get("name", "")))
        if len(cand) >= 6 and (target in cand or cand in target):
            return candidate
    return None


def get_geocoder() -> GeoapifyGeocodingClient | None:
    settings = get_settings()
    if settings.geoapify_api_key is None:
        return None
    return GeoapifyGeocodingClient(settings.geoapify_api_key.get_secret_value())


def _valid_coords(lat: float | None, lng: float | None) -> bool:
    return (
        lat is not None
        and lng is not None
        and -90.0 <= float(lat) <= 90.0
        and -180.0 <= float(lng) <= 180.0
    )


async def resolve_destination_centre(
    destination: str,
    *,
    known: tuple[float | None, float | None] = (None, None),
    ai_estimate: tuple[float | None, float | None] = (None, None),
    geocoder: GeoapifyGeocodingClient | None,
) -> tuple[tuple[float, float] | None, LocationSource]:
    """The reference point every stop is checked against. Trust order:
    the trip's own stored coordinates, then a live geocode of the
    destination text, then the model's estimate, else unknown."""
    if _valid_coords(*known):
        return (float(known[0]), float(known[1])), "poi"  # type: ignore[arg-type]
    if geocoder is not None:
        try:
            results = await geocoder.geocode(destination, limit=1)
        except PlacesProviderError:
            logger.warning("destination_geocode_failed", exc_info=True)
            results = []
        for result in results:
            if _valid_coords(result["lat"], result["lng"]):
                return (result["lat"], result["lng"]), "places_api"
    if _valid_coords(*ai_estimate):
        return (float(ai_estimate[0]), float(ai_estimate[1])), "ai_estimate"  # type: ignore[arg-type]
    return None, "unresolved"


class PlaceGrounder:
    def __init__(
        self,
        destination: str,
        centre: tuple[float, float] | None,
        candidates: list[dict[str, Any]],
        *,
        geocoder: GeoapifyGeocodingClient | None,
        pois_repo: PoisRepository | None = None,
        max_km: float = DEFAULT_MAX_KM,
    ) -> None:
        self.destination = destination
        self.centre = centre
        self.candidates = list(candidates)
        self._geocoder = geocoder
        self._pois_repo = pois_repo or PoisRepository()
        self.max_km = max_km
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT_GEOCODES)

    # -- step 1: the catalog --------------------------------------------------
    def _from_candidate(self, place: ProposedPlace, row: dict[str, Any]) -> GroundedPlace:
        return GroundedPlace(
            name=str(row["name"]),
            category=valid_category(row.get("category") or place.category),
            location_source="poi",
            poi_id=str(row["id"]),
            area=place.area,
            lat=row.get("lat"),
            lng=row.get("lng"),
            opening_hours=row.get("opening_hours"),
            avg_cost=float(row["avg_cost"]) if row.get("avg_cost") is not None else None,
        )

    async def _lookup_catalog(self, place: ProposedPlace) -> GroundedPlace | None:
        matched = match_candidate(place.name, self.candidates)
        if matched is not None:
            return self._from_candidate(place, matched)
        try:
            rows = await self._pois_repo.search_text(place.name, category=None, limit=5)
        except Exception:  # noqa: BLE001 - a catalog hiccup must not fail the plan
            logger.warning("place_grounding_catalog_lookup_failed", exc_info=True)
            return None
        nearby = [
            row
            for row in rows
            if within_km(self.centre, row.get("lat"), row.get("lng"), self.max_km)
        ]
        matched = match_candidate(place.name, nearby)
        return self._from_candidate(place, matched) if matched is not None else None

    # -- step 2: live geocoding ------------------------------------------------
    async def _geocode(self, place: ProposedPlace) -> GroundedPlace | None:
        if self._geocoder is None:
            return None
        query = ", ".join(part for part in (place.name, place.area, self.destination) if part)
        bias = self.centre
        try:
            async with self._semaphore:
                results = await self._geocoder.geocode(
                    query,
                    bias_lat=bias[0] if bias else None,
                    bias_lng=bias[1] if bias else None,
                    limit=3,
                )
        except PlacesProviderError:
            # Breaker: one outage, one warning, no per-place timeouts.
            logger.warning("place_grounding_geocoder_unavailable", exc_info=True)
            self._geocoder = None
            return None

        for result in results:
            if result.get("result_type") in _AREA_RESULT_TYPES:
                continue
            if float(result.get("confidence") or 0.0) < _MIN_GEOCODE_CONFIDENCE:
                continue
            if not within_km(self.centre, result["lat"], result["lng"], self.max_km):
                continue
            category = valid_category(place.category)
            cached = None
            if result.get("place_id"):
                try:
                    cached = await self._pois_repo.upsert_from_places_api(
                        {
                            "name": place.name,
                            "category": category,
                            "lat": result["lat"],
                            "lng": result["lng"],
                            "address": result.get("formatted"),
                            "city": result.get("city"),
                            "region": result.get("region"),
                            "opening_hours": None,
                            "external_ref": str(result["place_id"]),
                        }
                    )
                except Exception:  # noqa: BLE001 - caching is a bonus, not the result
                    logger.warning("place_grounding_cache_failed", exc_info=True)
            return GroundedPlace(
                name=place.name,
                category=category,
                location_source="places_api",
                poi_id=str(cached["id"]) if cached else None,
                area=place.area,
                lat=result["lat"],
                lng=result["lng"],
                opening_hours=None,
                avg_cost=None,
            )
        return None

    # -- steps 3-4: the model's own coordinates, or nothing ------------------
    def _from_estimate(self, place: ProposedPlace) -> GroundedPlace:
        category = valid_category(place.category)
        if _valid_coords(place.lat, place.lng) and within_km(
            self.centre, place.lat, place.lng, AI_ESTIMATE_MAX_KM
        ):
            return GroundedPlace(
                name=place.name,
                category=category,
                location_source="ai_estimate",
                area=place.area,
                lat=float(place.lat),  # type: ignore[arg-type]
                lng=float(place.lng),  # type: ignore[arg-type]
            )
        return GroundedPlace(
            name=place.name, category=category, location_source="unresolved", area=place.area
        )

    async def ground(self, place: ProposedPlace) -> GroundedPlace:
        if not place.name or not place.name.strip():
            return GroundedPlace(name="", category="other", location_source="unresolved")
        grounded = await self._lookup_catalog(place)
        if grounded is not None:
            return grounded
        grounded = await self._geocode(place)
        if grounded is not None:
            return grounded
        return self._from_estimate(place)

    async def ground_many(self, places: list[ProposedPlace]) -> list[GroundedPlace]:
        """Grounds every place concurrently (bounded by the semaphore) while
        preserving input order — one slow geocode never serializes the
        whole plan."""
        return list(await asyncio.gather(*(self.ground(place) for place in places)))
