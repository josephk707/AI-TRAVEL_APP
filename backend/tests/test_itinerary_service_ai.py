"""
Unit tests for the AI-first half of app/services/itinerary_service.py:
how the model's structured plan (named places with coordinates, or a
"destination not recognised" refusal) becomes persistable items. The
grounder is faked so no geocoding or database is involved; the real
end-to-end path is covered by tests/test_trips_api.py (real database,
fake gateway) and tests/test_llm_gateway_live.py (real Gemini).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.exceptions import BusinessRuleError
from app.services import itinerary_service
from app.services.itinerary_service import _GeneratedItem, _GeneratedItinerary
from app.services.place_grounding_service import GroundedPlace, ProposedPlace

_USER = "11111111-1111-4111-8111-111111111111"
_TRIP = "22222222-2222-4222-8222-222222222222"


class _FakeGrounder:
    def __init__(self, source: str = "places_api") -> None:
        self.source = source
        self.seen: list[ProposedPlace] = []

    async def ground_many(self, places: list[ProposedPlace]) -> list[GroundedPlace]:
        self.seen.extend(places)
        return [
            GroundedPlace(
                name=p.name,
                category=p.category or "other",
                location_source=self.source,  # type: ignore[arg-type]
                poi_id="cached-" + p.name if self.source == "places_api" else None,
                area=p.area,
                lat=p.lat,
                lng=p.lng,
            )
            for p in places
        ]


def _candidate() -> dict[str, Any]:
    return {
        "id": "poi-red-fort",
        "name": "Red Fort",
        "category": "heritage",
        "lat": 28.6562,
        "lng": 77.2410,
        "opening_hours": None,
        "avg_cost": 35,
    }


# ---------------------------------------------------------------------------
# schema hygiene
# ---------------------------------------------------------------------------
def test_generated_item_normalizes_times_and_rejects_nonsense() -> None:
    ok = _GeneratedItem(
        day_number=1, place_name="x", planned_start="9:5", estimated_duration_min=60
    )
    assert ok.planned_start == "09:05"
    with pytest.raises(ValueError):
        _GeneratedItem(
            day_number=1, place_name="x", planned_start="25:00", estimated_duration_min=60
        )
    with pytest.raises(ValueError):
        _GeneratedItem(
            day_number=1, place_name="x", planned_start="morning", estimated_duration_min=60
        )


# ---------------------------------------------------------------------------
# _ground_generated_items
# ---------------------------------------------------------------------------
async def test_named_places_are_grounded_and_candidate_indexes_map_directly() -> None:
    generated = _GeneratedItinerary(
        summary="s",
        items=[
            _GeneratedItem(
                day_number=1,
                place_name="Humayun's Tomb",
                area="Nizamuddin",
                category="heritage",
                lat=28.5933,
                lng=77.2506,
                planned_start="14:00",
                estimated_duration_min=90,
                estimated_cost=35,
                notes="Fits your heritage interest.",
            ),
            _GeneratedItem(
                day_number=1,
                candidate_index=0,
                planned_start="09:30",
                estimated_duration_min=120,
            ),
        ],
    )
    grounder = _FakeGrounder()

    items = await itinerary_service._ground_generated_items(generated, [_candidate()], grounder)

    assert [p.name for p in grounder.seen] == ["Humayun's Tomb"]
    # Ordered by start time within the day, sequence_order assigned accordingly.
    assert [(i["poi_name"], i["sequence_order"]) for i in items] == [
        ("Red Fort", 0),
        ("Humayun's Tomb", 1),
    ]
    red_fort, tomb = items
    assert red_fort["poi_id"] == "poi-red-fort"
    assert red_fort["location_source"] == "poi"
    assert red_fort["estimated_cost"] == 35.0  # catalog avg cost, no model estimate given
    assert tomb["poi_id"] == "cached-Humayun's Tomb"
    assert tomb["location_source"] == "places_api"
    assert (tomb["place_lat"], tomb["place_lng"]) == (28.5933, 77.2506)
    assert tomb["place_area"] == "Nizamuddin"
    assert tomb["estimated_cost"] == 35
    assert tomb["notes"] == "Fits your heritage interest."


async def test_hallucinated_index_without_a_name_is_dropped_but_a_name_still_grounds() -> None:
    generated = _GeneratedItinerary(
        summary="s",
        items=[
            _GeneratedItem(
                day_number=1, candidate_index=99, planned_start="09:00", estimated_duration_min=60
            ),
            _GeneratedItem(
                day_number=1,
                candidate_index=99,
                place_name="Lotus Temple",
                lat=28.5535,
                lng=77.2588,
                planned_start="11:00",
                estimated_duration_min=60,
            ),
            _GeneratedItem(day_number=2, planned_start="09:00", estimated_duration_min=60),
        ],
    )

    items = await itinerary_service._ground_generated_items(
        generated, [_candidate()], _FakeGrounder("ai_estimate")
    )

    assert [i["poi_name"] for i in items] == ["Lotus Temple"]
    assert items[0]["location_source"] == "ai_estimate"
    assert items[0]["poi_id"] is None


# ---------------------------------------------------------------------------
# generate_itinerary — destination not recognised
# ---------------------------------------------------------------------------
class _RefusingGateway:
    async def complete(self, messages, *, response_schema=None, config=None):  # noqa: ANN001
        from app.services.ai.llm_gateway import LLMResponse

        return LLMResponse(
            text="{}",
            parsed=_GeneratedItinerary(
                destination_recognized=False,
                clarification_question="I don't know a place called Xyzzyville — which country is it in?",
                summary="",
            ),
            model="fake",
        )


@pytest.fixture
def unknown_destination(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from datetime import date

    state: dict[str, Any] = {"replaced": False, "tracked": []}

    async def fake_get_trip(self, trip_id):  # noqa: ANN001
        return {
            "id": trip_id,
            "destination": "Xyzzyville",
            "destination_lat": None,
            "destination_lng": None,
            "budget_planned": 10000,
            "budget_currency": "INR",
            "start_date": date(2026, 10, 10),
            "end_date": date(2026, 10, 11),
        }

    async def fake_accessible(self, trip_id, user_id):  # noqa: ANN001
        return True

    async def fake_replace(self, trip_id, days):  # noqa: ANN001
        state["replaced"] = True

    async def fake_search(self, *a, **k):  # noqa: ANN001
        return []

    async def fake_profile(self, user_id):  # noqa: ANN001
        return {}

    async def fake_interest_ids(self, user_id):  # noqa: ANN001
        return []

    async def fake_list_interests(self):  # noqa: ANN001
        return []

    async def fake_personalization(user_id):  # noqa: ANN001
        return None

    async def fake_track(user_id, event, props=None):  # noqa: ANN001
        state["tracked"].append(event)

    R = "app.repositories."
    monkeypatch.setattr(R + "trips_repository.TripsRepository.get_trip", fake_get_trip)
    monkeypatch.setattr(R + "trips_repository.TripsRepository.is_trip_accessible", fake_accessible)
    monkeypatch.setattr(R + "trips_repository.TripsRepository.replace_itinerary", fake_replace)
    monkeypatch.setattr(R + "pois_repository.PoisRepository.search_text", fake_search)
    monkeypatch.setattr(R + "profiles_repository.ProfilesRepository.get_by_id", fake_profile)
    monkeypatch.setattr(
        R + "onboarding_repository.OnboardingRepository.get_interest_ids_for_profile",
        fake_interest_ids,
    )
    monkeypatch.setattr(
        R + "interests_repository.InterestsRepository.list_interests", fake_list_interests
    )
    monkeypatch.setattr(
        itinerary_service.personalization_service,
        "get_personalization_context",
        fake_personalization,
    )
    monkeypatch.setattr(itinerary_service.analytics_service, "track", fake_track)
    monkeypatch.setattr(itinerary_service, "get_llm_gateway", lambda: _RefusingGateway())
    return state


async def test_unknown_destination_asks_a_follow_up_and_persists_nothing(
    unknown_destination: dict[str, Any],
) -> None:
    from app.schemas.trips import ItineraryGenerateRequest

    with pytest.raises(BusinessRuleError) as excinfo:
        await itinerary_service.generate_itinerary(_TRIP, _USER, ItineraryGenerateRequest())

    error = excinfo.value
    assert error.code == "CLARIFICATION_NEEDED"
    assert "Xyzzyville" in str(error.message)
    assert error.details == {
        "missing_fields": ["destination"],
        "reason": "destination_unrecognized",
    }
    assert unknown_destination["replaced"] is False
    assert "itinerary_destination_unrecognized" in unknown_destination["tracked"]
