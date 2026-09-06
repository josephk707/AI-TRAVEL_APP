"""
Unit tests for app/services/personalization_service.py — the deterministic
template fallback (no Gemini configured), the "has any real signal" gate
(never fabricates a personality for a blank-slate user), and
get_personalization_context's real/None contract — exercised with
monkeypatched repositories, no real database or network. The real,
live-database + live-Gemini-when-configured path is covered separately in
tests/test_personalization_api.py.
"""

from __future__ import annotations

import pytest

from app.services import personalization_service


def _patch_repos(
    monkeypatch: pytest.MonkeyPatch,
    *,
    profile: dict | None = None,
    interest_ids: list[int] | None = None,
    interests: list[dict] | None = None,
    favorites: list[dict] | None = None,
    trips: list[dict] | None = None,
    signal_counts: dict[str, int] | None = None,
    upserted: dict | None = None,
) -> None:
    async def fake_get_by_id(self, user_id):  # noqa: ANN001
        return profile

    async def fake_get_interest_ids(self, user_id):  # noqa: ANN001
        return interest_ids or []

    async def fake_list_interests(self):  # noqa: ANN001
        return interests or []

    async def fake_list_favorites(self, user_id):  # noqa: ANN001
        return favorites or []

    async def fake_list_trips(self, user_id):  # noqa: ANN001
        return trips or []

    async def fake_get_signal_counts(self, user_id):  # noqa: ANN001
        return signal_counts or {}

    async def fake_upsert(self, user_id, preference_weights):  # noqa: ANN001
        if upserted is not None:
            upserted["value"] = preference_weights
        return {
            "user_id": user_id,
            "preference_weights": preference_weights,
            "updated_at": "2026-08-28T00:00:00Z",
        }

    monkeypatch.setattr(
        "app.repositories.profiles_repository.ProfilesRepository.get_by_id", fake_get_by_id
    )
    monkeypatch.setattr(
        "app.repositories.onboarding_repository.OnboardingRepository.get_interest_ids_for_profile",
        fake_get_interest_ids,
    )
    monkeypatch.setattr(
        "app.repositories.interests_repository.InterestsRepository.list_interests",
        fake_list_interests,
    )
    monkeypatch.setattr(
        "app.repositories.collections_repository.CollectionsRepository.list_favorites",
        fake_list_favorites,
    )
    monkeypatch.setattr(
        "app.repositories.trips_repository.TripsRepository.list_trips", fake_list_trips
    )
    monkeypatch.setattr(
        "app.repositories.personalization_repository.PersonalizationRepository.get_signal_counts",
        fake_get_signal_counts,
    )
    monkeypatch.setattr(
        "app.repositories.personalization_repository.PersonalizationRepository.upsert_profile",
        fake_upsert,
    )
    monkeypatch.setattr(personalization_service, "get_llm_gateway", lambda: None)


async def test_compute_travel_dna_for_a_blank_slate_user_never_invents_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_repos(monkeypatch, profile={})

    result = await personalization_service.compute_travel_dna(
        "11111111-1111-4111-8111-111111111111"
    )

    assert result["generated_by"] == "template"
    assert result["travel_personality"] == "New Explorer"
    assert "don't know your travel preferences yet" in result["summary"]
    assert result["interests"] == []
    assert result["trips_planned"] == 0


async def test_compute_travel_dna_uses_real_onboarding_answers_in_the_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_repos(
        monkeypatch,
        profile={
            "travel_style": "planned",
            "pace": "relaxed",
            "budget_bracket": "mid",
            "travel_companion": "family",
            "trip_motivation": "Trying real local food.",
        },
        interest_ids=[1],
        interests=[{"id": 1, "slug": "heritage", "label": "Heritage & History"}],
        favorites=[{"poi_category": "heritage"}, {"poi_category": "heritage"}],
        trips=[{"id": "t1"}],
    )

    result = await personalization_service.compute_travel_dna(
        "11111111-1111-4111-8111-111111111111"
    )

    assert result["generated_by"] == "template"
    assert result["interests"] == ["Heritage & History"]
    assert result["favorite_categories"] == {"heritage": 2}
    assert result["trips_planned"] == 1
    assert result["places_saved"] == 2
    # Real facts actually appear in the generated summary — not fabricated.
    assert "heritage" in result["summary"].lower()
    assert "planned" in result["summary"]


async def test_compute_travel_dna_persists_into_personalization_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upserted: dict = {}
    _patch_repos(
        monkeypatch,
        profile={"travel_style": "flexible"},
        upserted=upserted,
    )

    await personalization_service.compute_travel_dna("11111111-1111-4111-8111-111111111111")

    assert upserted["value"]["travel_style"] == "flexible"
    assert upserted["value"]["generated_by"] == "template"
    assert "summary" in upserted["value"]


async def test_get_personalization_context_returns_none_when_never_computed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_profile(self, user_id):  # noqa: ANN001
        return None

    monkeypatch.setattr(
        "app.repositories.personalization_repository.PersonalizationRepository.get_profile",
        fake_get_profile,
    )

    result = await personalization_service.get_personalization_context(
        "11111111-1111-4111-8111-111111111111"
    )

    assert result is None


async def test_get_personalization_context_builds_a_real_summary_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_profile(self, user_id):  # noqa: ANN001
        return {
            "preference_weights": {
                "summary": "You enjoy heritage sites and relaxed days.",
                "travel_companion": "family",
                "trip_motivation": "Trying real local food.",
            }
        }

    monkeypatch.setattr(
        "app.repositories.personalization_repository.PersonalizationRepository.get_profile",
        fake_get_profile,
    )

    result = await personalization_service.get_personalization_context(
        "11111111-1111-4111-8111-111111111111"
    )

    assert result is not None
    assert "You enjoy heritage sites" in result
    assert "family" in result
