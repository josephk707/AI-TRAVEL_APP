"""
Real Google Places API (New) client — the ONLY place in this codebase that
talks to Google Maps Platform, per CLAUDE.md §7's "every external call site
goes through an abstraction" convention (mirrors the LLM Gateway pattern
`AI_ARCHITECTURE.md` prescribes for AI providers).

Never called with a client-supplied API key, and the key itself never
reaches the client — `app/api/v1/pois.py` proxies through this, per
`API_SPECIFICATION.md` §5 ("never exposes the raw Maps API key to the
client") and `MOBILE_ARCHITECTURE.md` §8.

Every method raises `PlacesProviderError` (never a raw httpx exception) on
ANY failure — timeout, non-2xx, malformed JSON, missing required fields —
so the service layer has exactly one failure mode to handle and degrade
gracefully around (CLAUDE.md §9). Nothing here persists to the database;
that is `app/services/poi_service.py`'s job, so this client stays a thin,
swappable transport layer.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("app.google_places")

_BASE_URL = "https://places.googleapis.com/v1"
_DEFAULT_TIMEOUT_SECONDS = 8.0

# Field masks are REQUIRED by Places API (New) — an omitted mask is
# rejected outright. Kept minimal (only what `poi_service.py` actually
# maps into a `pois` row) per CLAUDE.md §8's "receive only the context
# necessary" principle, applied here to outbound field selection too: no
# indiscriminate over-fetching from the provider.
_PLACE_FIELDS = (
    "id,displayName,formattedAddress,location,types,regularOpeningHours,addressComponents"
)
_SEARCH_FIELD_MASK = ",".join(f"places.{field}" for field in _PLACE_FIELDS.split(","))
_DETAIL_FIELD_MASK = _PLACE_FIELDS


class PlacesProviderError(Exception):
    """Raised for any Google Places failure — timeout, HTTP error, or a
    malformed response. Carries no raw provider exception message in its
    own `str()` beyond a short, safe summary, so a caller that logs this
    exception's message never risks echoing back sensitive upstream detail
    (the API key is sent as a header, never embedded in a URL or body, so
    it cannot appear in any error text this class produces)."""


class GooglePlacesClient:
    def __init__(self, api_key: str, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self, field_mask: str) -> dict[str, str]:
        return {
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": field_mask,
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, field_mask: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{_BASE_URL}/{path}", headers=self._headers(field_mask), json=body
                )
        except httpx.TimeoutException as exc:
            raise PlacesProviderError("Google Places request timed out.") from exc
        except httpx.HTTPError as exc:
            raise PlacesProviderError("Google Places request failed.") from exc

        if response.status_code != 200:
            logger.warning(
                "google_places_non_200", extra={"status": response.status_code, "path": path}
            )
            raise PlacesProviderError(f"Google Places returned HTTP {response.status_code}.")

        try:
            return response.json()
        except ValueError as exc:
            raise PlacesProviderError("Google Places returned a malformed response.") from exc

    async def search_text(self, query: str, max_results: int = 20) -> list[dict[str, Any]]:
        """`places:searchText` — used for `GET /v1/pois/search`'s free-text
        query mode."""
        body: dict[str, Any] = {"textQuery": query, "maxResultCount": max_results}
        data = await self._post("places:searchText", _SEARCH_FIELD_MASK, body)
        places = data.get("places", [])
        if not isinstance(places, list):
            raise PlacesProviderError("Google Places search response had an unexpected shape.")
        return places

    async def search_nearby(
        self,
        lat: float,
        lng: float,
        radius_m: float,
        included_types: list[str] | None = None,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """`places:searchNearby` — used for `GET /v1/pois/nearby`."""
        body: dict[str, Any] = {
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": radius_m,
                }
            },
            "maxResultCount": max_results,
        }
        if included_types:
            body["includedTypes"] = included_types
        data = await self._post("places:searchNearby", _SEARCH_FIELD_MASK, body)
        places = data.get("places", [])
        if not isinstance(places, list):
            raise PlacesProviderError("Google Places nearby response had an unexpected shape.")
        return places

    async def get_place(self, place_id: str) -> dict[str, Any]:
        """`places/{id}` detail lookup — used to refresh/backfill a single
        cached POI's data (`external_ref` round-trip)."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    f"{_BASE_URL}/places/{place_id}",
                    headers=self._headers(_DETAIL_FIELD_MASK),
                )
        except httpx.TimeoutException as exc:
            raise PlacesProviderError("Google Places request timed out.") from exc
        except httpx.HTTPError as exc:
            raise PlacesProviderError("Google Places request failed.") from exc

        if response.status_code != 200:
            raise PlacesProviderError(f"Google Places returned HTTP {response.status_code}.")

        try:
            return response.json()
        except ValueError as exc:
            raise PlacesProviderError("Google Places returned a malformed response.") from exc
