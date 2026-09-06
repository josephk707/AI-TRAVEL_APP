"""
Final Personalization phase — the Personalization Engine.

    User
     -> Explicit preferences (onboarding: profiles.travel_style/pace/
        budget_bracket/travel_companion/trip_motivation)
     -> Interests (profile_interests, source-tagged 'onboarding'/'inferred')
     -> Travel behaviour/signals (feedback_signals — already logged today
        by F17 post-trip feedback and by favoriting, see
        collections_service.py/feedback_service.py; never invasive
        tracking, just the app's own existing real interaction events)
     -> Personalization profile (personalization_profile.preference_weights,
        computed here — structured, not one big text blob)
     -> Gemini (personalization.py's prompt, same LLMGateway every other
        AI pipeline uses — no second AI system)
     -> Personalized recommendations (itinerary_service.py reads this
        module's `get_personalization_context()`)

Deliberately NOT a machine-learning pipeline (CLAUDE.md-equivalent
instruction for this phase, explicit): no embeddings computed, no model
trained. "Learning the user" means aggregating real counts and reusing
the existing Gemini call for one short natural-language summary — nothing
more.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from app.repositories.collections_repository import CollectionsRepository
from app.repositories.interests_repository import InterestsRepository
from app.repositories.onboarding_repository import OnboardingRepository
from app.repositories.personalization_repository import PersonalizationRepository
from app.repositories.profiles_repository import ProfilesRepository
from app.repositories.trips_repository import TripsRepository
from app.services.ai.factory import get_llm_gateway
from app.services.ai.llm_gateway import GenerationConfig, LLMMessage, LLMProviderError, MessageRole
from app.services.ai.prompts import personalization as personalization_prompts

logger = logging.getLogger("app.services.personalization")

_POSITIVE_SIGNALS = {"accept", "thumbs_up", "review_submitted"}


class _TravelDnaResult(BaseModel):
    travel_personality: str
    summary: str


async def _gather_facts(user_id: str) -> dict[str, Any]:
    profile = await ProfilesRepository().get_by_id(user_id)
    profile = profile or {}

    interest_ids = await OnboardingRepository().get_interest_ids_for_profile(user_id)
    all_interests = {i["id"]: i["label"] for i in await InterestsRepository().list_interests()}
    interest_labels = [all_interests[i] for i in interest_ids if i in all_interests]

    favorites = await CollectionsRepository().list_favorites(user_id)
    favorite_categories: dict[str, int] = {}
    for fav in favorites:
        category = fav.get("poi_category")
        if category:
            favorite_categories[category] = favorite_categories.get(category, 0) + 1

    trips = await TripsRepository().list_trips(user_id)

    signal_counts = await PersonalizationRepository().get_signal_counts(user_id)
    positive_signal_count = sum(
        n for signal, n in signal_counts.items() if signal in _POSITIVE_SIGNALS
    )

    return {
        "travel_style": profile.get("travel_style"),
        "pace": profile.get("pace"),
        "budget_bracket": profile.get("budget_bracket"),
        "travel_companion": profile.get("travel_companion"),
        "trip_motivation": profile.get("trip_motivation"),
        "interests": interest_labels,
        "favorite_categories": favorite_categories,
        "trips_planned": len(trips),
        "places_saved": len(favorites),
        "positive_signal_count": positive_signal_count,
        "signal_counts": signal_counts,
    }


def _has_any_real_signal(facts: dict[str, Any]) -> bool:
    return bool(
        facts["travel_style"]
        or facts["pace"]
        or facts["budget_bracket"]
        or facts["travel_companion"]
        or facts["trip_motivation"]
        or facts["interests"]
        or facts["favorite_categories"]
        or facts["trips_planned"]
    )


def _deterministic_summary(facts: dict[str, Any]) -> _TravelDnaResult:
    """Real, honest fallback when Gemini is unavailable — built purely
    from the same facts the AI prompt would have received, never
    fabricated (CLAUDE.md §8's "never trust/never invent" applies equally
    to a template as to a model)."""
    if not _has_any_real_signal(facts):
        return _TravelDnaResult(
            travel_personality="New Explorer",
            summary=(
                "We don't know your travel preferences yet. Complete onboarding or start "
                "exploring — your Travel DNA builds itself from what you actually tell us "
                "and do in the app."
            ),
        )

    parts: list[str] = []
    if facts["interests"]:
        parts.append(f"you're drawn to {', '.join(facts['interests'][:3]).lower()}")
    if facts["travel_style"]:
        parts.append(f"you prefer a {facts['travel_style']} travel style")
    if facts["pace"]:
        parts.append(f"a {facts['pace']} pace")
    if facts["budget_bracket"]:
        parts.append(f"{facts['budget_bracket']}-conscious travel")
    if facts["travel_companion"]:
        parts.append(f"usually travelling {facts['travel_companion']}")

    summary = (
        "Based on what you've told us, " + "; ".join(parts) + "."
        if parts
        else ("You've started building your travel profile — keep exploring to refine it.")
    )
    if facts["places_saved"]:
        summary += f" You've saved {facts['places_saved']} place(s) so far."

    label = facts["interests"][0] if facts["interests"] else (facts["travel_style"] or "Traveller")
    return _TravelDnaResult(travel_personality=f"{label.title()} Explorer", summary=summary)


async def compute_travel_dna(user_id: str) -> dict[str, Any]:
    """Always recomputes fresh (cheap: a handful of indexed count queries
    plus, when available, one short Gemini call) — no separate caching
    layer, per this phase's explicit "don't overengineer" instruction.
    The result is still persisted into `personalization_profile` so
    `get_personalization_context()` (used by itinerary generation) has a
    real, structured value to read even between recomputes."""
    facts = await _gather_facts(user_id)

    gateway = get_llm_gateway()
    generated_by = "template"
    dna = _deterministic_summary(facts)

    if gateway is not None and _has_any_real_signal(facts):
        try:
            response = await gateway.complete(
                [
                    LLMMessage(MessageRole.SYSTEM, personalization_prompts.SYSTEM_PROMPT),
                    LLMMessage(MessageRole.USER, personalization_prompts.build_user_message(facts)),
                ],
                response_schema=_TravelDnaResult,
                config=GenerationConfig(
                    temperature=0.6, max_output_tokens=512, timeout_seconds=15.0
                ),
            )
            assert isinstance(response.parsed, _TravelDnaResult)
            dna = response.parsed
            generated_by = "ai"
        except LLMProviderError:
            logger.warning("travel_dna_llm_failed_using_template", exc_info=True)

    preference_weights = {
        "travel_style": facts["travel_style"],
        "pace": facts["pace"],
        "budget_bracket": facts["budget_bracket"],
        "travel_companion": facts["travel_companion"],
        "trip_motivation": facts["trip_motivation"],
        "interests": facts["interests"],
        "favorite_categories": facts["favorite_categories"],
        "trips_planned": facts["trips_planned"],
        "places_saved": facts["places_saved"],
        "positive_signal_count": facts["positive_signal_count"],
        "travel_personality": dna.travel_personality,
        "summary": dna.summary,
        "generated_by": generated_by,
    }
    saved = await PersonalizationRepository().upsert_profile(user_id, preference_weights)

    return {
        "travel_style": facts["travel_style"],
        "pace": facts["pace"],
        "budget_bracket": facts["budget_bracket"],
        "travel_companion": facts["travel_companion"],
        "trip_motivation": facts["trip_motivation"],
        "interests": facts["interests"],
        "favorite_categories": facts["favorite_categories"],
        "trips_planned": facts["trips_planned"],
        "places_saved": facts["places_saved"],
        "travel_personality": dna.travel_personality,
        "summary": dna.summary,
        "generated_by": generated_by,
        "updated_at": saved["updated_at"],
    }


async def get_personalization_context(user_id: str) -> str | None:
    """Cheap, synchronous-shaped read for itinerary_service.py to inject
    into its own AI prompt — reads the LAST COMPUTED `personalization_profile`
    row (if any) rather than recomputing/calling Gemini a second time on
    the hot itinerary-generation path. Returns None (never a placeholder
    string) when nothing has been computed yet, e.g. a brand-new user who
    hasn't opened their Travel DNA screen — itinerary generation degrades
    to exactly its pre-existing behavior in that case."""
    row = await PersonalizationRepository().get_profile(user_id)
    if row is None:
        return None
    weights = row.get("preference_weights") or {}
    if not isinstance(weights, dict) or not weights.get("summary"):
        return None

    lines = [f"Known traveller preferences: {weights['summary']}"]
    if weights.get("travel_companion"):
        lines.append(f"Usually travels: {weights['travel_companion']}")
    if weights.get("trip_motivation"):
        lines.append(f"What makes a trip special for them: {weights['trip_motivation']}")
    return " ".join(lines)
