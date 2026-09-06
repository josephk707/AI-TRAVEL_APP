"""
Unit tests for app/services/onboarding_service.py's business logic —
interest-id validation and the FR-003 exception flow (save failure never
blocks the caller; a background retry is scheduled instead) — exercised
with monkeypatched repositories, no real database or network. The real
database write path is covered separately (and for real) in
tests/test_onboarding_api.py.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import AppError, UpstreamUnavailableError
from app.core.security import AuthenticatedUser
from app.schemas.onboarding import OnboardingResponsesRequest
from app.services import onboarding_service

_USER = AuthenticatedUser(
    id="11111111-1111-4111-8111-111111111111", email="a@example.com", role="authenticated"
)

_KNOWN_INTERESTS = [
    {"id": 1, "slug": "heritage", "label": "Heritage & History"},
    {"id": 2, "slug": "food", "label": "Food & Cuisine"},
]


def _patch_known_interests(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_interests(self):  # noqa: ANN001
        return _KNOWN_INTERESTS

    monkeypatch.setattr(
        "app.repositories.interests_repository.InterestsRepository.list_interests",
        fake_list_interests,
    )


async def test_list_interests_returns_the_curated_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_known_interests(monkeypatch)

    result = await onboarding_service.list_interests()

    assert [i.slug for i in result] == ["heritage", "food"]


async def test_submit_responses_rejects_unknown_interest_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_known_interests(monkeypatch)
    payload = OnboardingResponsesRequest(interest_ids=[1, 999], pace="relaxed")

    with pytest.raises(AppError) as exc_info:
        await onboarding_service.submit_responses(_USER, payload)

    assert exc_info.value.code == "INVALID_INTEREST_IDS"
    assert exc_info.value.status_code == 400
    assert exc_info.value.details["unknown_interest_ids"] == [999]


async def test_submit_responses_allows_an_empty_interest_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty interest_ids must never be rejected — this is the FR-003
    "skip" alternative flow's shape (a user who skips still calls this
    endpoint with nothing selected, or never calls it at all)."""
    _patch_known_interests(monkeypatch)

    async def fake_save(
        self,
        profile_id,
        *,
        interest_ids,
        travel_style,
        pace,
        budget_bracket,
        travel_companion=None,
        trip_motivation=None,
    ):  # noqa: ANN001
        return {
            "onboarding_completed_at": "2026-08-25T00:00:00Z",
            "travel_style": travel_style,
            "pace": pace,
            "budget_bracket": budget_bracket,
            "travel_companion": travel_companion,
            "trip_motivation": trip_motivation,
        }

    async def fake_get_ids(self, profile_id):  # noqa: ANN001
        return []

    monkeypatch.setattr(
        "app.repositories.onboarding_repository.OnboardingRepository.save_onboarding_responses",
        fake_save,
    )
    monkeypatch.setattr(
        "app.repositories.onboarding_repository.OnboardingRepository.get_interest_ids_for_profile",
        fake_get_ids,
    )

    data, saved = await onboarding_service.submit_responses(
        _USER, OnboardingResponsesRequest(interest_ids=[])
    )

    assert saved is True
    assert data.interest_ids == []


async def test_submit_responses_on_db_failure_returns_saved_false_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The core FR-003 exception-flow guarantee: a save failure must never
    surface as a hard error to the caller — the endpoint (and this service
    function) must return a normal result with saved=False so the router
    can respond 202 and schedule a retry, never propagate the DB error."""
    _patch_known_interests(monkeypatch)

    async def failing_save(
        self,
        profile_id,
        *,
        interest_ids,
        travel_style,
        pace,
        budget_bracket,
        travel_companion=None,
        trip_motivation=None,
    ):  # noqa: ANN001
        raise UpstreamUnavailableError("simulated DB failure")

    monkeypatch.setattr(
        "app.repositories.onboarding_repository.OnboardingRepository.save_onboarding_responses",
        failing_save,
    )

    payload = OnboardingResponsesRequest(interest_ids=[1], pace="packed", budget_bracket="mid")
    data, saved = await onboarding_service.submit_responses(_USER, payload)

    assert saved is False
    assert data.onboarding_completed is False
    # The submitted values are echoed back as the (unconfirmed) pending
    # state, not silently discarded.
    assert data.interest_ids == [1]
    assert data.pace == "packed"
    assert data.budget_bracket == "mid"


async def test_retry_save_in_background_swallows_a_second_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The background retry must never raise into the caller (FastAPI's
    BackgroundTasks runner) even if the retry itself also fails — it can
    only log, per the module's own docstring."""
    monkeypatch.setattr("app.services.onboarding_service._BACKGROUND_RETRY_DELAY_SECONDS", 0)

    async def failing_save(
        self,
        profile_id,
        *,
        interest_ids,
        travel_style,
        pace,
        budget_bracket,
        travel_companion=None,
        trip_motivation=None,
    ):  # noqa: ANN001
        raise UpstreamUnavailableError("still failing")

    monkeypatch.setattr(
        "app.repositories.onboarding_repository.OnboardingRepository.save_onboarding_responses",
        failing_save,
    )

    # Must not raise.
    await onboarding_service.retry_save_in_background(
        _USER.id, OnboardingResponsesRequest(interest_ids=[])
    )


async def test_retry_save_in_background_succeeds_when_the_retry_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.onboarding_service._BACKGROUND_RETRY_DELAY_SECONDS", 0)
    calls: list[str] = []

    async def working_save(
        self,
        profile_id,
        *,
        interest_ids,
        travel_style,
        pace,
        budget_bracket,
        travel_companion=None,
        trip_motivation=None,
    ):  # noqa: ANN001
        calls.append(profile_id)
        return {
            "onboarding_completed_at": "2026-08-25T00:00:00Z",
            "travel_style": travel_style,
            "pace": pace,
            "budget_bracket": budget_bracket,
            "travel_companion": travel_companion,
            "trip_motivation": trip_motivation,
        }

    monkeypatch.setattr(
        "app.repositories.onboarding_repository.OnboardingRepository.save_onboarding_responses",
        working_save,
    )

    await onboarding_service.retry_save_in_background(
        _USER.id, OnboardingResponsesRequest(interest_ids=[])
    )

    assert calls == [_USER.id]


async def test_submit_responses_persists_companion_and_motivation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Final Personalization phase — the two new onboarding questions
    round-trip through the same save path as the original four."""
    _patch_known_interests(monkeypatch)
    captured: dict = {}

    async def fake_save(
        self,
        profile_id,
        *,
        interest_ids,
        travel_style,
        pace,
        budget_bracket,
        travel_companion=None,
        trip_motivation=None,
    ):  # noqa: ANN001
        captured["travel_companion"] = travel_companion
        captured["trip_motivation"] = trip_motivation
        return {
            "onboarding_completed_at": "2026-08-25T00:00:00Z",
            "travel_style": travel_style,
            "pace": pace,
            "budget_bracket": budget_bracket,
            "travel_companion": travel_companion,
            "trip_motivation": trip_motivation,
        }

    async def fake_get_ids(self, profile_id):  # noqa: ANN001
        return []

    monkeypatch.setattr(
        "app.repositories.onboarding_repository.OnboardingRepository.save_onboarding_responses",
        fake_save,
    )
    monkeypatch.setattr(
        "app.repositories.onboarding_repository.OnboardingRepository.get_interest_ids_for_profile",
        fake_get_ids,
    )

    payload = OnboardingResponsesRequest(
        interest_ids=[],
        travel_companion="family",
        trip_motivation="Trying real local food and learning the history behind places.",
    )
    data, saved = await onboarding_service.submit_responses(_USER, payload)

    assert saved is True
    assert captured["travel_companion"] == "family"
    assert (
        captured["trip_motivation"]
        == "Trying real local food and learning the history behind places."
    )
    assert data.travel_companion == "family"
