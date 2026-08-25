"""
Business logic for /v1/pois/* — F6 Maps & Navigation
(IMPLEMENTATION_BLUEPRINT.md F6, API_SPECIFICATION.md §5).

Search policy (documented decision, CLAUDE.md §13 — the PRD/API spec do not
spell out the exact cache-vs-live sequencing, only that the endpoint is "a
backend-cached proxy over Google Places"):
  1. Always query the local `pois` cache first — curated + previously
     cached `places_api` rows, real data, works even with no configured
     Google Maps API key.
  2. If a text `query` was given AND Google Maps is configured AND the
     cache returned fewer than `_LIVE_AUGMENT_THRESHOLD` results, also
     call Google Places live, validate each result, and cache genuinely
     new discoveries into `pois` (`source='places_api'`) so the next
     identical search is cache-only.
  3. If Google Maps is not configured, or the live call itself fails, the
     endpoint still returns the cache results — degraded, not broken
     (CLAUDE.md §9) — with `meta.degraded_mode` telling the client live
     search is temporarily unavailable rather than silently pretending
     the catalog is complete.

`GET /pois/nearby` is intentionally DB-only (no live call) per
API_SPECIFICATION.md §5's own description ("ST_DWithin query against
pois.location") — nearby is the fast, cheap, frequently-polled path (e.g.
future on-trip companion use, F7), so it must not carry Google Places
latency/cost on every call.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.repositories.pois_repository import PoisRepository
from app.schemas.poi import PoiNearbyQuery, PoiSearchQuery
from app.services.google_places_client import GooglePlacesClient, PlacesProviderError

logger = logging.getLogger("app.services.poi")

_LIVE_AUGMENT_THRESHOLD = 3

# Google's place `types` are far more granular than our 6-value category
# enum (DATABASE_SCHEMA.md §pois CHECK constraint) — this maps the most
# common tourism-relevant types down to it. Checked in this priority order
# (a place can carry multiple types; the first match wins) so a place
# tagged both "restaurant" and "point_of_interest" lands under the more
# specific "restaurant", not the generic "attraction" catch-all.
_TYPE_TO_CATEGORY: list[tuple[str, str]] = [
    ("restaurant", "restaurant"),
    ("cafe", "restaurant"),
    ("bakery", "restaurant"),
    ("bar", "restaurant"),
    ("meal_takeaway", "restaurant"),
    ("meal_delivery", "restaurant"),
    ("food", "restaurant"),
    ("hindu_temple", "heritage"),
    ("mosque", "heritage"),
    ("church", "heritage"),
    ("synagogue", "heritage"),
    ("place_of_worship", "heritage"),
    ("historical_landmark", "heritage"),
    ("monument", "heritage"),
    ("museum", "heritage"),
    ("park", "nature"),
    ("natural_feature", "nature"),
    ("campground", "nature"),
    ("zoo", "nature"),
    ("aquarium", "nature"),
    ("shopping_mall", "shopping"),
    ("clothing_store", "shopping"),
    ("market", "shopping"),
    ("supermarket", "shopping"),
    ("store", "shopping"),
    ("tourist_attraction", "attraction"),
    ("amusement_park", "attraction"),
    ("art_gallery", "attraction"),
    ("point_of_interest", "attraction"),
]


def _map_category(types: list[str]) -> str:
    type_set = set(types)
    for google_type, category in _TYPE_TO_CATEGORY:
        if google_type in type_set:
            return category
    return "other"


def _to_row_dict(poi: dict[str, Any]) -> dict[str, Any]:
    """Presents a repository row (which carries separate `lat`/`lng` columns
    from the `ST_Y`/`ST_X` projection in PoisRepository) in the nested
    `location: {lat, lng}` shape `PoiResponse` expects."""
    row = dict(poi)
    row["id"] = str(row["id"])
    row["location"] = {"lat": row.pop("lat"), "lng": row.pop("lng")}
    return row


def _validate_and_map_google_place(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Returns a repository-ready dict, or None if the provider result is
    missing data this application requires — a malformed/incomplete AI- or
    third-party-provider result is never persisted (CLAUDE.md §8), it is
    just skipped, with the rest of the batch still processed."""
    place_id = raw.get("id")
    display_name = raw.get("displayName", {})
    name = display_name.get("text") if isinstance(display_name, dict) else None
    location = raw.get("location", {})
    lat = location.get("latitude") if isinstance(location, dict) else None
    lng = location.get("longitude") if isinstance(location, dict) else None

    if not place_id or not name or lat is None or lng is None:
        logger.warning("google_places_result_skipped_incomplete", extra={"place_id": place_id})
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        logger.warning("google_places_result_skipped_bad_coords", extra={"place_id": place_id})
        return None

    types = raw.get("types", [])
    opening_hours = raw.get("regularOpeningHours")
    address_components = raw.get("addressComponents", [])
    city = None
    region = None
    if isinstance(address_components, list):
        for component in address_components:
            comp_types = component.get("types", [])
            if "locality" in comp_types and city is None:
                city = component.get("longText")
            if "administrative_area_level_1" in comp_types and region is None:
                region = component.get("longText")

    return {
        "name": name,
        "category": _map_category(types if isinstance(types, list) else []),
        "lat": float(lat),
        "lng": float(lng),
        "address": raw.get("formattedAddress"),
        "city": city,
        "region": region,
        "opening_hours": opening_hours if isinstance(opening_hours, dict) else None,
        "external_ref": place_id,
    }


async def search(params: PoiSearchQuery) -> tuple[list[dict[str, Any]], bool]:
    """Returns (results, degraded). `degraded=True` means live search was
    skipped (not configured or failed) — the cache results returned are
    still real, just possibly incomplete relative to the full live catalog."""
    repo = PoisRepository()

    if params.query:
        cached = await repo.search_text(params.query, params.category)
    else:
        assert params.lat is not None and params.lng is not None
        cached = await repo.search_nearby(params.lat, params.lng, params.radius_m, params.category)

    if not params.query or len(cached) >= _LIVE_AUGMENT_THRESHOLD:
        return [_to_row_dict(row) for row in cached], False

    settings = get_settings()
    if settings.google_maps_api_key is None:
        logger.info("poi_search_degraded", extra={"reason": "not_configured"})
        return [_to_row_dict(row) for row in cached], True

    client = GooglePlacesClient(settings.google_maps_api_key.get_secret_value())
    try:
        live_results = await client.search_text(params.query)
    except PlacesProviderError:
        logger.warning("poi_search_live_call_failed", exc_info=True)
        return [_to_row_dict(row) for row in cached], True

    known_refs = {row["external_ref"] for row in cached if row.get("external_ref")}
    merged = list(cached)
    for raw_place in live_results:
        mapped = _validate_and_map_google_place(raw_place)
        if mapped is None or mapped["external_ref"] in known_refs:
            continue
        if params.category and mapped["category"] != params.category:
            continue
        cached_row = await repo.upsert_from_places_api(mapped)
        merged.append(cached_row)
        known_refs.add(mapped["external_ref"])

    return [_to_row_dict(row) for row in merged], False


async def get_by_id(poi_id: str) -> dict[str, Any]:
    repo = PoisRepository()
    try:
        row = await repo.get_by_id(poi_id)
    except ValueError as exc:
        # uuid.UUID() rejects a malformed id — treated as "not found" rather
        # than a raw 500, since a syntactically invalid id can never match a
        # real row anyway (no format detail is meaningfully more helpful to
        # the client than a plain 404 here).
        raise NotFoundError("This place could not be found.") from exc
    if row is None:
        raise NotFoundError("This place could not be found.")
    return _to_row_dict(row)


async def nearby(params: PoiNearbyQuery) -> list[dict[str, Any]]:
    repo = PoisRepository()
    rows = await repo.search_nearby(params.lat, params.lng, params.radius_m, params.category)
    return [_to_row_dict(row) for row in rows]
