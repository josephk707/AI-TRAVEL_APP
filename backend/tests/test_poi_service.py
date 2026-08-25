"""
Unit tests for app/services/poi_service.py's business logic — category
mapping, Google-result validation, and the cache-first/live-augment search
policy documented in that module's own docstring — exercised with
monkeypatched repositories/provider client, no real database or network.
The real database path (cache reads, live cache-writes against the actual
Google Places API) is covered separately in tests/test_pois_api.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.schemas.poi import PoiNearbyQuery, PoiSearchQuery
from app.services import poi_service
from app.services.google_places_client import GooglePlacesClient, PlacesProviderError


def test_map_category_prefers_the_most_specific_matching_type() -> None:
    assert poi_service._map_category(["point_of_interest", "restaurant"]) == "restaurant"
    assert poi_service._map_category(["hindu_temple", "point_of_interest"]) == "heritage"
    assert poi_service._map_category(["park"]) == "nature"
    assert poi_service._map_category(["shopping_mall"]) == "shopping"
    assert poi_service._map_category(["tourist_attraction"]) == "attraction"


def test_map_category_falls_back_to_other_for_unknown_types() -> None:
    assert poi_service._map_category(["some_unknown_google_type"]) == "other"
    assert poi_service._map_category([]) == "other"


def _valid_raw_place(**overrides: object) -> dict:
    base = {
        "id": "ChIJ_valid",
        "displayName": {"text": "Valid Place"},
        "formattedAddress": "1 Real St",
        "location": {"latitude": 27.17, "longitude": 78.04},
        "types": ["tourist_attraction"],
        "addressComponents": [
            {"longText": "Agra", "types": ["locality"]},
            {"longText": "Uttar Pradesh", "types": ["administrative_area_level_1"]},
        ],
    }
    base.update(overrides)
    return base


def test_validate_and_map_google_place_extracts_expected_fields() -> None:
    mapped = poi_service._validate_and_map_google_place(_valid_raw_place())

    assert mapped is not None
    assert mapped["name"] == "Valid Place"
    assert mapped["category"] == "attraction"
    assert mapped["lat"] == 27.17
    assert mapped["lng"] == 78.04
    assert mapped["city"] == "Agra"
    assert mapped["region"] == "Uttar Pradesh"
    assert mapped["external_ref"] == "ChIJ_valid"


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": None},
        {"displayName": {}},
        {"location": {}},
        {"location": {"latitude": 999, "longitude": 78.04}},
        {"location": {"latitude": 27.17, "longitude": -999}},
    ],
)
def test_validate_and_map_google_place_rejects_incomplete_or_invalid_data(
    overrides: dict,
) -> None:
    """A malformed/incomplete provider result must never be persisted
    (CLAUDE.md §8) — it is skipped, not crashed on and not silently
    coerced into fake defaults."""
    assert poi_service._validate_and_map_google_place(_valid_raw_place(**overrides)) is None


_CACHED_ROW = {
    "id": "11111111-1111-4111-8111-111111111111",
    "name": "Cached Place",
    "category": "heritage",
    "lat": 27.17,
    "lng": 78.04,
    "address": "cached address",
    "city": "Agra",
    "region": "Uttar Pradesh",
    "country": "India",
    "opening_hours": None,
    "avg_cost": None,
    "source": "curated",
    "external_ref": None,
    "is_heritage_flagship": True,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}


def _patch_settings(monkeypatch: pytest.MonkeyPatch, api_key: str | None) -> None:
    fake_settings = SimpleNamespace(google_maps_api_key=SecretStr(api_key) if api_key else None)
    monkeypatch.setattr(poi_service, "get_settings", lambda: fake_settings)


async def test_search_by_nearby_never_calls_the_live_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search_nearby(self, lat, lng, radius_m, category, limit=20):  # noqa: ANN001
        return [dict(_CACHED_ROW)]

    monkeypatch.setattr(
        "app.repositories.pois_repository.PoisRepository.search_nearby", fake_search_nearby
    )

    def explode(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError(
            "GooglePlacesClient must not be constructed for a nearby-shaped search"
        )

    monkeypatch.setattr(poi_service, "GooglePlacesClient", explode)

    results, degraded = await poi_service.search(
        PoiSearchQuery(lat=27.17, lng=78.04, radius_m=2000)
    )

    assert degraded is False
    assert len(results) == 1
    assert results[0]["location"] == {"lat": 27.17, "lng": 78.04}


async def test_search_by_text_with_enough_cached_results_skips_live_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search_text(self, query, category, limit=20):  # noqa: ANN001
        return [dict(_CACHED_ROW) for _ in range(poi_service._LIVE_AUGMENT_THRESHOLD)]

    monkeypatch.setattr(
        "app.repositories.pois_repository.PoisRepository.search_text", fake_search_text
    )

    def explode(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("live provider must not be called when cache already has enough")

    monkeypatch.setattr(poi_service, "GooglePlacesClient", explode)

    results, degraded = await poi_service.search(PoiSearchQuery(query="heritage"))

    assert degraded is False
    assert len(results) == poi_service._LIVE_AUGMENT_THRESHOLD


async def test_search_by_text_degrades_when_provider_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search_text(self, query, category, limit=20):  # noqa: ANN001
        return []

    monkeypatch.setattr(
        "app.repositories.pois_repository.PoisRepository.search_text", fake_search_text
    )
    _patch_settings(monkeypatch, api_key=None)

    results, degraded = await poi_service.search(PoiSearchQuery(query="nonexistent place"))

    assert results == []
    assert degraded is True


async def test_search_by_text_degrades_when_provider_call_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search_text(self, query, category, limit=20):  # noqa: ANN001
        return []

    monkeypatch.setattr(
        "app.repositories.pois_repository.PoisRepository.search_text", fake_search_text
    )
    _patch_settings(monkeypatch, api_key="fake-key")

    async def failing_live_search(self, query, max_results=20):  # noqa: ANN001
        raise PlacesProviderError("simulated provider outage")

    monkeypatch.setattr(GooglePlacesClient, "search_text", failing_live_search)

    results, degraded = await poi_service.search(PoiSearchQuery(query="anything"))

    assert results == []
    assert degraded is True


async def test_search_by_text_merges_and_caches_new_live_discoveries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search_text(self, query, category, limit=20):  # noqa: ANN001
        return []

    upserted: list[dict] = []

    async def fake_upsert(self, poi):  # noqa: ANN001
        upserted.append(poi)
        return {**_CACHED_ROW, "external_ref": poi["external_ref"], "source": "places_api"}

    monkeypatch.setattr(
        "app.repositories.pois_repository.PoisRepository.search_text", fake_search_text
    )
    monkeypatch.setattr(
        "app.repositories.pois_repository.PoisRepository.upsert_from_places_api", fake_upsert
    )
    _patch_settings(monkeypatch, api_key="fake-key")

    async def fake_live_search(self, query, max_results=20):  # noqa: ANN001
        return [_valid_raw_place(id="ChIJ_new_discovery")]

    monkeypatch.setattr(GooglePlacesClient, "search_text", fake_live_search)

    results, degraded = await poi_service.search(PoiSearchQuery(query="valid place"))

    assert degraded is False
    assert len(results) == 1
    assert len(upserted) == 1
    assert upserted[0]["external_ref"] == "ChIJ_new_discovery"


async def test_search_skips_live_results_already_present_in_the_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached_with_ref = {**_CACHED_ROW, "external_ref": "ChIJ_already_cached", "source": "places_api"}

    async def fake_search_text(self, query, category, limit=20):  # noqa: ANN001
        return [dict(cached_with_ref)]

    async def explode_upsert(self, poi):  # noqa: ANN001
        raise AssertionError("must not re-upsert a place already present in the cache")

    monkeypatch.setattr(
        "app.repositories.pois_repository.PoisRepository.search_text", fake_search_text
    )
    monkeypatch.setattr(
        "app.repositories.pois_repository.PoisRepository.upsert_from_places_api", explode_upsert
    )
    _patch_settings(monkeypatch, api_key="fake-key")

    async def fake_live_search(self, query, max_results=20):  # noqa: ANN001
        return [_valid_raw_place(id="ChIJ_already_cached")]

    monkeypatch.setattr(GooglePlacesClient, "search_text", fake_live_search)

    results, degraded = await poi_service.search(PoiSearchQuery(query="valid place"))

    assert degraded is False
    assert len(results) == 1


async def test_nearby_returns_mapped_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search_nearby(self, lat, lng, radius_m, category, limit=20):  # noqa: ANN001
        return [dict(_CACHED_ROW)]

    monkeypatch.setattr(
        "app.repositories.pois_repository.PoisRepository.search_nearby", fake_search_nearby
    )

    results = await poi_service.nearby(PoiNearbyQuery(lat=27.17, lng=78.04))

    assert len(results) == 1
    assert results[0]["location"] == {"lat": 27.17, "lng": 78.04}


async def test_get_by_id_raises_not_found_for_a_missing_poi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.exceptions import NotFoundError

    async def fake_get_by_id(self, poi_id):  # noqa: ANN001
        return None

    monkeypatch.setattr("app.repositories.pois_repository.PoisRepository.get_by_id", fake_get_by_id)

    with pytest.raises(NotFoundError):
        await poi_service.get_by_id("11111111-1111-4111-8111-111111111111")


async def test_get_by_id_raises_not_found_for_a_malformed_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        await poi_service.get_by_id("not-a-valid-uuid")
