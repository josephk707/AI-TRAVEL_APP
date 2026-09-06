"""
Real Geoapify Places API (v2) client — added alongside (not replacing)
`google_places_client.py`, per CLAUDE.md §7's "every external call site
goes through an abstraction" convention. Same shape and same failure
contract as the Google client so `poi_service.py` can treat either
provider identically.

Scope, as explicitly authorized (Maps Integration phase): Places only.
Geoapify's Places API v2 has NO free-text query parameter — resolving a
typed query like "Taj Mahal" into a location requires Geoapify's
Geocoding API, which is a SEPARATE product this phase was explicitly
told not to assume is enabled. This client therefore only implements
location-based ("nearby") search — real, live, and exactly what
`GET /v1/pois/nearby` needs; it does not and cannot power a free-text
search box without geocoding. See docs/PHASE_STATUS.md's Maps
Integration phase entry for the full capability audit (what Geocoding /
Reverse Geocoding / Routing / Route Matrix would each additionally
require).

Raises the SAME `PlacesProviderError` type `google_places_client.py`
defines — both genuinely mean "the live places provider failed", so
`poi_service.py` handles either with one except clause rather than two
near-identical ones.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.google_places_client import PlacesProviderError

logger = logging.getLogger("app.geoapify_places")

_BASE_URL = "https://api.geoapify.com/v2/places"
_DEFAULT_TIMEOUT_SECONDS = 8.0

# Geoapify's `categories` parameter is REQUIRED (unlike Google, which
# defaults to "anything nearby") — this is the curated default used when
# the caller didn't ask for one specific app category, chosen to cover
# every category this app's own PoiCategory enum maps results into.
_DEFAULT_CATEGORIES = (
    "tourism,heritage,catering,entertainment,commercial.shopping_mall,natural,leisure.park"
)

# app PoiCategory -> Geoapify category taxonomy, used to narrow the
# request when the caller specified a category filter.
_APP_CATEGORY_TO_GEOAPIFY: dict[str, str] = {
    "heritage": "heritage,tourism.sights,religion",
    "restaurant": "catering",
    "attraction": "tourism.attraction,entertainment",
    "nature": "natural,leisure.park",
    "shopping": "commercial.shopping_mall,commercial.marketplace",
    "other": _DEFAULT_CATEGORIES,
}


class GeoapifyPlacesClient:
    def __init__(self, api_key: str, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def search_nearby(
        self,
        lat: float,
        lng: float,
        radius_m: float,
        category: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """`GET /v2/places?filter=circle:...` — real radius search around a
        point. Returns the raw list of GeoJSON `Feature` dicts (each with a
        `properties` object) exactly as Geoapify returns them; mapping into
        this app's POI shape happens in `poi_service.py`, matching how the
        Google client stays a thin transport layer."""
        categories = (
            _APP_CATEGORY_TO_GEOAPIFY.get(category, _DEFAULT_CATEGORIES)
            if category
            else _DEFAULT_CATEGORIES
        )
        params: dict[str, str | int] = {
            "categories": categories,
            "filter": f"circle:{lng},{lat},{int(radius_m)}",
            "bias": f"proximity:{lng},{lat}",
            "limit": limit,
            "apiKey": self._api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(_BASE_URL, params=params)
        except httpx.TimeoutException as exc:
            raise PlacesProviderError("Geoapify Places request timed out.") from exc
        except httpx.HTTPError as exc:
            raise PlacesProviderError("Geoapify Places request failed.") from exc

        if response.status_code != 200:
            logger.warning("geoapify_places_non_200", extra={"status": response.status_code})
            raise PlacesProviderError(f"Geoapify Places returned HTTP {response.status_code}.")

        try:
            data = response.json()
        except ValueError as exc:
            raise PlacesProviderError("Geoapify Places returned a malformed response.") from exc

        features = data.get("features")
        if not isinstance(features, list):
            raise PlacesProviderError("Geoapify Places response had an unexpected shape.")
        return features
