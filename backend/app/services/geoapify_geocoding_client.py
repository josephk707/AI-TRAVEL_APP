"""
Real Geoapify Geocoding API (v1) client — the free-text half that
`geoapify_places_client.py` deliberately did not implement (its module
docstring records that Places v2 has no free-text query parameter and that
geocoding is a separate Geoapify product). Verified live against the
project's configured key on 2026-09-06 (a request for "Humayun's Tomb,
Delhi, India" returned the real monument with `match_type=full_match`),
so this is a genuine integration, not an assumed one.

Used by `place_grounding_service.py` to turn a model-proposed place name
("Humayun's Tomb", area "Nizamuddin") into verified coordinates before an
itinerary stop is persisted (CLAUDE.md §8: never trust a model response
blindly). Same thin-transport contract and the same `PlacesProviderError`
failure type as the two Places clients, so callers handle every live
provider identically.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.google_places_client import PlacesProviderError

logger = logging.getLogger("app.geoapify_geocoding")

_BASE_URL = "https://api.geoapify.com/v1/geocode/search"
_DEFAULT_TIMEOUT_SECONDS = 6.0


class GeoapifyGeocodingClient:
    def __init__(self, api_key: str, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def geocode(
        self,
        text: str,
        *,
        bias_lat: float | None = None,
        bias_lng: float | None = None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """`GET /v1/geocode/search?text=...` — free-text forward geocoding.
        `bias_*` nudges ranking towards the destination centre so "City
        Palace" resolves to the one in the traveller's city, not another
        country's. Returns normalized result dicts (name, formatted, lat,
        lng, place_id, result_type, confidence, match_type, city, region,
        country) — never the raw provider shape, so the grounding service
        is provider-agnostic."""
        params: dict[str, str | int] = {
            "text": text,
            "limit": limit,
            "apiKey": self._api_key,
        }
        if bias_lat is not None and bias_lng is not None:
            params["bias"] = f"proximity:{bias_lng},{bias_lat}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(_BASE_URL, params=params)
        except httpx.TimeoutException as exc:
            raise PlacesProviderError("Geoapify Geocoding request timed out.") from exc
        except httpx.HTTPError as exc:
            raise PlacesProviderError("Geoapify Geocoding request failed.") from exc

        if response.status_code != 200:
            logger.warning("geoapify_geocoding_non_200", extra={"status": response.status_code})
            raise PlacesProviderError(f"Geoapify Geocoding returned HTTP {response.status_code}.")

        try:
            data = response.json()
        except ValueError as exc:
            raise PlacesProviderError("Geoapify Geocoding returned a malformed response.") from exc

        features = data.get("features")
        if not isinstance(features, list):
            raise PlacesProviderError("Geoapify Geocoding response had an unexpected shape.")

        results: list[dict[str, Any]] = []
        for feature in features:
            props = feature.get("properties") if isinstance(feature, dict) else None
            if not isinstance(props, dict):
                continue
            lat, lng = props.get("lat"), props.get("lon")
            if lat is None or lng is None:
                continue
            rank = props.get("rank") if isinstance(props.get("rank"), dict) else {}
            results.append(
                {
                    "name": props.get("name"),
                    "formatted": props.get("formatted"),
                    "lat": float(lat),
                    "lng": float(lng),
                    "place_id": props.get("place_id"),
                    "result_type": props.get("result_type"),
                    "confidence": float(rank.get("confidence") or 0.0),
                    "match_type": rank.get("match_type"),
                    "city": props.get("city"),
                    "region": props.get("state"),
                    "country": props.get("country"),
                }
            )
        return results
