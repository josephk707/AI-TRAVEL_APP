"""
Unit tests for app/services/modification_service.py's prompt-assembly
contract (AI_ARCHITECTURE.md §4 step 1), exercised with monkeypatched
repositories and a fake gateway — no real database, no real Gemini call.
The real end-to-end path (real token, real database, real Gemini) is
covered separately in tests/test_llm_gateway_live.py.

These lock in two behaviours that were MISSING and were found by running
the real pipeline against the real Gemini API:

  * the traveller's own profile never reached the prompt, so a request
    like "add one historical place that matches my interests" could only
    ever produce a clarifying question;
  * the trip's `ai_conversations` history never reached the prompt
    (`get_recent_messages` existed but had no caller), so when the model
    asked a clarifying question the traveller's answer arrived with no
    memory of the question — an unbreakable clarification loop.
"""

from __future__ import annotations

from datetime import time
from typing import Any

import pytest

from app.services import modification_service
from app.services.ai.llm_gateway import LLMResponse, MessageRole

_USER = "11111111-1111-4111-8111-111111111111"
_TRIP = "22222222-2222-4222-8222-222222222222"


# ---------------------------------------------------------------------------
# _build_profile_block
# ---------------------------------------------------------------------------
def test_profile_block_carries_interests_style_and_pace() -> None:
    block = modification_service._build_profile_block(
        {"travel_style": "flexible", "pace": "relaxed"}, ["Heritage & History", "Art & Culture"]
    )

    assert "Heritage & History" in block
    assert "Art & Culture" in block
    assert "flexible" in block
    assert "relaxed" in block


def test_profile_block_is_empty_for_a_traveller_with_no_preferences_yet() -> None:
    """A brand-new traveller degrades to exactly the previous behaviour —
    no empty placeholder headings are sent to the model."""
    assert modification_service._build_profile_block({}, []) == ""
    assert modification_service._build_profile_block({"travel_style": None, "pace": None}, "") == ""


# ---------------------------------------------------------------------------
# Prompt assembly — history + profile
# ---------------------------------------------------------------------------
class _CapturingGateway:
    """Records the exact message list the service hands the provider."""

    def __init__(self) -> None:
        self.messages: list[Any] = []

    async def complete(self, messages, *, response_schema=None, config=None):  # noqa: ANN001
        self.messages = list(messages)
        return LLMResponse(
            text="{}",
            parsed=modification_service._ModificationResult(
                reply="Noted.", clarification_needed=False, changes=[]
            ),
            model="fake-model",
        )


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> _CapturingGateway:
    gateway = _CapturingGateway()
    history = [
        {"role": "assistant", "content": "An older reply that opens the window."},
        {"role": "user", "content": "Add one historical place that matches my interests."},
        {
            "role": "assistant",
            "content": "Which day would you like to add this historical visit to?",
        },
    ]

    async def fake_get_trip(self, trip_id):  # noqa: ANN001
        return {"id": trip_id, "destination": "Agra, India"}

    async def fake_accessible(self, trip_id, user_id):  # noqa: ANN001
        return True

    async def fake_itinerary(self, trip_id):  # noqa: ANN001
        return [{"day_number": 1, "items": []}]

    async def fake_conversation(self, user_id, trip_id):  # noqa: ANN001
        return "33333333-3333-4333-8333-333333333333"

    async def fake_recent(self, conversation_id, limit=20):  # noqa: ANN001
        return history

    async def fake_log(self, *a, **k):  # noqa: ANN001
        return None

    async def fake_search(self, *a, **k):  # noqa: ANN001
        return [{"id": "poi-1", "name": "Agra Fort", "category": "heritage", "avg_cost": 50}]

    async def fake_profile(self, user_id):  # noqa: ANN001
        return {"travel_style": "flexible", "pace": "relaxed", "preferred_language": None}

    async def fake_interest_ids(self, user_id):  # noqa: ANN001
        return [1]

    async def fake_list_interests(self):  # noqa: ANN001
        return [{"id": 1, "slug": "heritage", "label": "Heritage & History"}]

    R = "app.repositories."
    monkeypatch.setattr(R + "trips_repository.TripsRepository.get_trip", fake_get_trip)
    monkeypatch.setattr(R + "trips_repository.TripsRepository.is_trip_accessible", fake_accessible)
    monkeypatch.setattr(R + "trips_repository.TripsRepository.get_itinerary", fake_itinerary)
    monkeypatch.setattr(
        R + "ai_conversations_repository.AiConversationsRepository.get_or_create_conversation",
        fake_conversation,
    )
    monkeypatch.setattr(
        R + "ai_conversations_repository.AiConversationsRepository.get_recent_messages",
        fake_recent,
    )
    monkeypatch.setattr(
        R + "ai_conversations_repository.AiConversationsRepository.log_message", fake_log
    )
    monkeypatch.setattr(R + "pois_repository.PoisRepository.search_text", fake_search)
    monkeypatch.setattr(R + "profiles_repository.ProfilesRepository.get_by_id", fake_profile)
    monkeypatch.setattr(
        R + "onboarding_repository.OnboardingRepository.get_interest_ids_for_profile",
        fake_interest_ids,
    )
    monkeypatch.setattr(
        R + "interests_repository.InterestsRepository.list_interests", fake_list_interests
    )
    monkeypatch.setattr(modification_service, "get_llm_gateway", lambda: gateway)
    return gateway


async def test_prior_conversation_turns_are_replayed_to_the_model(
    captured: _CapturingGateway,
) -> None:
    """AI_ARCHITECTURE.md §4 step 1 — without this, a traveller answering
    the model's own clarifying question is answering into a void."""
    await modification_service.modify_itinerary(_TRIP, _USER, "Day 2 please.")

    contents = [m.content for m in captured.messages]
    assert "Add one historical place that matches my interests." in contents
    assert "Which day would you like to add this historical visit to?" in contents


async def test_history_window_never_opens_on_an_assistant_turn(
    captured: _CapturingGateway,
) -> None:
    """The window is the last N rows, so it can begin mid-exchange; a
    conversation opening with a model turn is rejected by the provider."""
    await modification_service.modify_itinerary(_TRIP, _USER, "Day 2 please.")

    after_system = [m for m in captured.messages if m.role is not MessageRole.SYSTEM]
    assert after_system[0].role is MessageRole.USER
    assert "An older reply that opens the window." not in [m.content for m in captured.messages]


async def test_current_message_is_not_duplicated_out_of_history(
    captured: _CapturingGateway,
) -> None:
    """History is read BEFORE the current turn is logged, so the request's
    own message must appear exactly once — in the final turn."""
    await modification_service.modify_itinerary(_TRIP, _USER, "Day 2 please.")

    assert sum("Day 2 please." in m.content for m in captured.messages) == 1
    assert captured.messages[-1].role is MessageRole.USER
    assert "Day 2 please." in captured.messages[-1].content


async def test_traveller_profile_reaches_the_final_prompt(captured: _CapturingGateway) -> None:
    await modification_service.modify_itinerary(_TRIP, _USER, "Add somewhere historical.")

    final = captured.messages[-1].content
    assert "Heritage & History" in final
    assert "relaxed" in final
    # The itinerary/candidate context is still there — the profile block is
    # additive, not a replacement.
    assert "CANDIDATE PLACE LIST" in final


# ---------------------------------------------------------------------------
# _introduces_new_conflict — mixed time types
# ---------------------------------------------------------------------------
def _day_with_two_stored_items() -> list[dict[str, Any]]:
    """Exactly what `TripsRepository.get_itinerary` returns: asyncpg hands
    back `datetime.time` for a `time` column, not "HH:MM" strings."""
    return [
        {
            "day_number": 1,
            "items": [
                {
                    "id": "item-a",
                    "poi_name": "Taj Mahal",
                    "planned_start": time(9, 0),
                    "planned_end": time(11, 0),
                    "day_number": 1,
                },
                {
                    "id": "item-b",
                    "poi_name": "Agra Fort",
                    "planned_start": time(14, 0),
                    "planned_end": time(16, 0),
                    "day_number": 1,
                },
            ],
        }
    ]


def test_conflict_check_survives_a_model_string_time_beside_stored_time_objects() -> None:
    """Regression guard: the proposed item carries the model's "HH:MM"
    string while its siblings carry `datetime.time`. Sorting those raw
    values raised `TypeError: '<' not supported between instances of
    'datetime.time' and 'str'` — a 500 reaching the app the moment a
    traveller moved one stop on a day that held two."""
    days = _day_with_two_stored_items()
    existing = days[0]["items"][1]
    proposed = dict(existing, planned_start="15:00", planned_end="17:00")

    assert modification_service._introduces_new_conflict(days, existing, proposed) is False


def test_conflict_check_detects_a_real_new_overlap() -> None:
    """And it still does its actual job — the deterministic validator, not
    the model, decides whether a change is allowed (AI_ARCHITECTURE.md §4
    step 3-4). Moving Agra Fort onto 10:00 overlaps the Taj Mahal visit
    that runs until 11:00."""
    days = _day_with_two_stored_items()
    existing = days[0]["items"][1]
    proposed = dict(existing, planned_start="10:00", planned_end="12:00")

    assert modification_service._introduces_new_conflict(days, existing, proposed) is True
