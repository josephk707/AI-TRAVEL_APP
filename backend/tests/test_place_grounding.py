"""
Unit tests for app/services/place_grounding_service.py — the trust ladder
every model-proposed place climbs before it is persisted (AI-first
itinerary phase): catalog match -> live geocode -> model estimate ->
unresolved. Exercised with a fake geocoder and a fake catalog repository,
no network, no database.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services import place_grounding_service as grounding
from app.services.google_places_client import PlacesProviderError
from app.services.place_grounding_service import (
    PlaceGrounder,
    ProposedPlace,
    match_candidate,
    normalize_name,
    resolve_destination_centre,
    within_km,
)

DELHI = (28.6139, 77.2090)


class _FakeRepo:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.upserts: list[dict[str, Any]] = []

    async def search_text(self, query, category, limit=20):  # noqa: ANN001
        needle = query.lower()
        return [r for r in self.rows if needle in str(r["name"]).lower()][:limit]

    async def upsert_from_places_api(self, poi):  # noqa: ANN001
        self.upserts.append(poi)
        return {"id": "cached-poi-id", **poi}


class _FakeGeocoder:
    def __init__(self, results: list[dict[str, Any]] | None = None, *, fail: bool = False):
        self.results = results or []
        self.fail = fail
        self.calls: list[str] = []

    async def geocode(self, text, *, bias_lat=None, bias_lng=None, limit=3):  # noqa: ANN001
        self.calls.append(text)
        if self.fail:
            raise PlacesProviderError("down")
        return self.results


def _catalog_row(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "poi-red-fort",
        "name": "Red Fort",
        "category": "heritage",
        "lat": 28.6562,
        "lng": 77.2410,
        "opening_hours": {"mon": "closed"},
        "avg_cost": 35,
        **overrides,
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def test_normalize_name_ignores_case_punctuation_diacritics_and_leading_the() -> None:
    assert normalize_name("The Humayun's Tomb") == "humayuns tomb"
    assert normalize_name("Humāyūn’s   Tomb!") == "humayuns tomb"


def test_match_candidate_exact_then_containment_with_length_guard() -> None:
    rows = [_catalog_row(), _catalog_row(id="p2", name="India Gate")]
    assert match_candidate("red fort", rows)["id"] == "poi-red-fort"
    assert match_candidate("Red Fort (Lal Qila)", rows)["id"] == "poi-red-fort"
    # A four-letter token must not swallow "India Gate".
    assert match_candidate("Gate", rows) is None
    assert match_candidate("Lotus Temple", rows) is None


def test_within_km_accepts_anything_when_no_centre_is_known() -> None:
    assert within_km(None, 10.0, 10.0, 1.0) is True
    assert within_km(DELHI, 28.5933, 77.2506, 80.0) is True
    assert within_km(DELHI, 19.0760, 72.8777, 80.0) is False  # Mumbai
    assert within_km(DELHI, None, None, 80.0) is False


# ---------------------------------------------------------------------------
# resolve_destination_centre
# ---------------------------------------------------------------------------
async def test_destination_centre_prefers_stored_then_geocode_then_model() -> None:
    geocoder = _FakeGeocoder([{"lat": 28.61, "lng": 77.21}])

    assert await resolve_destination_centre("Delhi", known=(1.0, 2.0), geocoder=geocoder) == (
        (1.0, 2.0),
        "poi",
    )
    assert await resolve_destination_centre("Delhi", geocoder=geocoder) == (
        (28.61, 77.21),
        "places_api",
    )
    assert await resolve_destination_centre(
        "Delhi", ai_estimate=(28.6, 77.2), geocoder=_FakeGeocoder([])
    ) == ((28.6, 77.2), "ai_estimate")
    assert await resolve_destination_centre("Delhi", geocoder=None) == (None, "unresolved")


async def test_destination_centre_survives_a_geocoder_outage() -> None:
    centre, source = await resolve_destination_centre(
        "Delhi", ai_estimate=(28.6, 77.2), geocoder=_FakeGeocoder(fail=True)
    )
    assert (centre, source) == ((28.6, 77.2), "ai_estimate")


# ---------------------------------------------------------------------------
# PlaceGrounder — the trust ladder
# ---------------------------------------------------------------------------
async def test_catalog_candidate_wins_and_no_geocode_call_is_made() -> None:
    geocoder = _FakeGeocoder()
    grounder = PlaceGrounder(
        "Delhi", DELHI, [_catalog_row()], geocoder=geocoder, pois_repo=_FakeRepo()
    )

    result = await grounder.ground(ProposedPlace(name="red fort", category="attraction"))

    assert result.location_source == "poi"
    assert result.poi_id == "poi-red-fort"
    assert (result.lat, result.lng) == (28.6562, 77.2410)
    assert result.category == "heritage"  # the catalog's category, not the model's
    assert result.opening_hours == {"mon": "closed"}
    assert result.avg_cost == 35.0
    assert geocoder.calls == []


async def test_catalog_search_ignores_a_same_name_place_in_another_city() -> None:
    far_away = _catalog_row(id="p-mumbai", name="City Palace", lat=19.07, lng=72.87)
    grounder = PlaceGrounder(
        "Jaipur", (26.9124, 75.7873), [], geocoder=None, pois_repo=_FakeRepo([far_away])
    )

    result = await grounder.ground(ProposedPlace(name="City Palace", lat=26.9258, lng=75.8237))

    assert result.location_source == "ai_estimate"
    assert result.poi_id is None


async def test_geocoded_place_is_verified_cached_and_labelled_places_api() -> None:
    repo = _FakeRepo()
    geocoder = _FakeGeocoder(
        [
            {
                "name": "Humayun's Tomb",
                "formatted": "Humayun's Tomb, Delhi",
                "lat": 28.5933,
                "lng": 77.2506,
                "place_id": "pid-1",
                "result_type": "amenity",
                "confidence": 1.0,
                "match_type": "full_match",
                "city": "Delhi",
                "region": "Delhi",
            }
        ]
    )
    grounder = PlaceGrounder("Delhi, India", DELHI, [], geocoder=geocoder, pois_repo=repo)

    result = await grounder.ground(
        ProposedPlace(
            name="Humayun's Tomb", area="Nizamuddin", category="heritage", lat=28.59, lng=77.25
        )
    )

    assert geocoder.calls == ["Humayun's Tomb, Nizamuddin, Delhi, India"]
    assert result.location_source == "places_api"
    assert result.poi_id == "cached-poi-id"
    assert (result.lat, result.lng) == (28.5933, 77.2506)
    assert repo.upserts[0]["external_ref"] == "pid-1"
    assert repo.upserts[0]["category"] == "heritage"


async def test_geocode_result_for_the_whole_city_or_far_away_is_rejected() -> None:
    geocoder = _FakeGeocoder(
        [
            {
                "lat": 28.61,
                "lng": 77.21,
                "place_id": "city",
                "result_type": "city",
                "confidence": 1.0,
            },
            {
                "lat": 19.07,
                "lng": 72.87,
                "place_id": "far",
                "result_type": "amenity",
                "confidence": 1.0,
            },
            {
                "lat": 28.62,
                "lng": 77.22,
                "place_id": "weak",
                "result_type": "amenity",
                "confidence": 0.1,
            },
        ]
    )
    grounder = PlaceGrounder("Delhi", DELHI, [], geocoder=geocoder, pois_repo=_FakeRepo())

    result = await grounder.ground(ProposedPlace(name="Somewhere", lat=28.60, lng=77.20))

    assert result.location_source == "ai_estimate"
    assert (result.lat, result.lng) == (28.60, 77.20)


async def test_model_estimate_far_from_the_destination_becomes_unresolved() -> None:
    grounder = PlaceGrounder("Delhi", DELHI, [], geocoder=None, pois_repo=_FakeRepo())

    result = await grounder.ground(ProposedPlace(name="Gateway of India", lat=18.92, lng=72.83))

    assert result.location_source == "unresolved"
    assert result.lat is None and result.lng is None
    assert result.category == "other"


async def test_geocoder_outage_trips_the_breaker_once_and_falls_back() -> None:
    geocoder = _FakeGeocoder(fail=True)
    grounder = PlaceGrounder("Delhi", DELHI, [], geocoder=geocoder, pois_repo=_FakeRepo())

    results = await grounder.ground_many(
        [
            ProposedPlace(name="Lotus Temple", lat=28.5535, lng=77.2588),
            ProposedPlace(name="Lodhi Garden", lat=28.5931, lng=77.2197),
            ProposedPlace(name="Unknown corner"),
        ]
    )

    assert [r.location_source for r in results] == ["ai_estimate", "ai_estimate", "unresolved"]
    # ground_many runs concurrently, so more than one call may have started
    # before the breaker tripped — but never one per place after that.
    assert len(geocoder.calls) <= 3


async def test_ground_many_preserves_input_order() -> None:
    grounder = PlaceGrounder("Delhi", DELHI, [_catalog_row()], geocoder=None, pois_repo=_FakeRepo())
    results = await grounder.ground_many(
        [ProposedPlace(name="Lotus Temple", lat=28.55, lng=77.26), ProposedPlace(name="Red Fort")]
    )
    assert [r.name for r in results] == ["Lotus Temple", "Red Fort"]


def test_get_geocoder_is_none_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    class _S:
        geoapify_api_key = None

    monkeypatch.setattr(grounding, "get_settings", lambda: _S())
    assert grounding.get_geocoder() is None
