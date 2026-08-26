"""
F3 — AI Conversational Planner & Personalised Itinerary Generation
(IMPLEMENTATION_BLUEPRINT.md F3, AI_ARCHITECTURE.md §2, API_SPECIFICATION.md §4).

Pipeline, matching AI_ARCHITECTURE.md §2 exactly:
  1. Assemble context (profile + interests, request payload, own notes)
  2. Candidate POI retrieval (rule-based: destination match; embedding
     similarity is deferred — see Known Limitations, PHASE_STATUS.md)
  3. LLM composition (Gemini, structured output, candidate-index-only —
     see prompts/itinerary.py for why this makes hallucinated venues
     structurally impossible, not just prompt-discouraged)
  4. Business-rule validation (app/services/business_rules.py) — deterministic
  5. Persist trips/itinerary_days/itinerary_items; set generation_status
  6. Return to client

Failure handling (FR-001 exception flow): any LLM failure — not configured,
timeout, malformed output — serves the deterministic fallback scheduler
(`_build_fallback_itinerary`, real candidate POIs, no AI call, no
fabrication) and sets `generation_status='fallback_used'` with
`meta.degraded_mode=True`. This is a hard requirement (CLAUDE.md §3), not
an optimization.
"""

from __future__ import annotations

import logging
from datetime import date as date_cls
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field

from app.core.exceptions import BusinessRuleError, ForbiddenError, NotFoundError
from app.repositories.interests_repository import InterestsRepository
from app.repositories.onboarding_repository import OnboardingRepository
from app.repositories.pois_repository import PoisRepository
from app.repositories.profiles_repository import ProfilesRepository
from app.repositories.trips_repository import TripsRepository
from app.schemas.trips import ItineraryGenerateRequest
from app.services import analytics_service, business_rules
from app.services.ai.factory import get_llm_gateway
from app.services.ai.llm_gateway import GenerationConfig, LLMMessage, LLMProviderError, MessageRole
from app.services.ai.prompts import itinerary as itinerary_prompts

logger = logging.getLogger("app.services.itinerary")

_MAX_CANDIDATES = 30
_MAX_DAYS = 21


class _GeneratedItem(BaseModel):
    day_number: int = Field(ge=1, le=_MAX_DAYS)
    candidate_index: int = Field(ge=0)
    planned_start: str
    estimated_duration_min: int = Field(ge=15, le=600)
    notes: str | None = None


class _GeneratedItinerary(BaseModel):
    summary: str
    items: list[_GeneratedItem] = Field(default_factory=list)


async def _load_context(user_id: str) -> dict[str, Any]:
    profile = await ProfilesRepository().get_by_id(user_id)
    interest_ids = await OnboardingRepository().get_interest_ids_for_profile(user_id)
    all_interests = {i["id"]: i["label"] for i in await InterestsRepository().list_interests()}
    interest_labels = [all_interests[i] for i in interest_ids if i in all_interests]
    return {"profile": profile or {}, "interest_labels": interest_labels}


async def _get_candidates(destination: str, limit: int = _MAX_CANDIDATES) -> list[dict[str, Any]]:
    city_token = destination.split(",")[0].strip()
    repo = PoisRepository()
    candidates = await repo.search_text(city_token, category=None, limit=limit)
    return candidates


def _day_dates(start_date: date_cls | None, day_count: int) -> dict[int, date_cls | None]:
    if start_date is None:
        return {n: None for n in range(1, day_count + 1)}
    return {n: start_date + timedelta(days=n - 1) for n in range(1, day_count + 1)}


def _build_fallback_itinerary(
    candidates: list[dict[str, Any]], day_count: int
) -> list[dict[str, Any]]:
    """The pre-authored, non-AI fallback (AI_ARCHITECTURE.md §2 "Failure
    handling"): a deterministic greedy scheduler over REAL candidate POIs
    already in the database (curated + previously cached — never invented),
    ordered heritage-flagship-first (PoisRepository.search_text's own
    ordering). No LLM call is made on this path at all."""
    items: list[dict[str, Any]] = []
    per_day = max(1, min(4, len(candidates) // max(day_count, 1) or 1))
    cursor = 0
    start_slots = ["09:00", "12:00", "15:00", "18:00"]
    for day_number in range(1, day_count + 1):
        for slot_index in range(per_day):
            if cursor >= len(candidates):
                break
            candidate = candidates[cursor]
            cursor += 1
            duration = 120
            items.append(
                {
                    "day_number": day_number,
                    "poi_id": str(candidate["id"]),
                    "poi_name": candidate["name"],
                    "poi_lat": candidate["lat"],
                    "poi_lng": candidate["lng"],
                    "poi_category": candidate["category"],
                    "poi_opening_hours": candidate.get("opening_hours"),
                    "poi_avg_cost": candidate.get("avg_cost"),
                    "estimated_cost": candidate.get("avg_cost"),
                    "planned_start": start_slots[slot_index % len(start_slots)],
                    "estimated_duration_min": duration,
                    "sequence_order": slot_index,
                    "source": "ai",
                    "notes": None,
                }
            )
    return items


def _map_generated_items(
    generated: _GeneratedItinerary, candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    day_sequence: dict[int, int] = {}
    for gen_item in generated.items:
        if gen_item.candidate_index < 0 or gen_item.candidate_index >= len(candidates):
            logger.warning(
                "itinerary_generation_hallucinated_index_rejected",
                extra={"candidate_index": gen_item.candidate_index},
            )
            continue
        candidate = candidates[gen_item.candidate_index]
        seq = day_sequence.get(gen_item.day_number, 0)
        day_sequence[gen_item.day_number] = seq + 1
        items.append(
            {
                "day_number": gen_item.day_number,
                "poi_id": str(candidate["id"]),
                "poi_name": candidate["name"],
                "poi_lat": candidate["lat"],
                "poi_lng": candidate["lng"],
                "poi_category": candidate["category"],
                "poi_opening_hours": candidate.get("opening_hours"),
                "poi_avg_cost": candidate.get("avg_cost"),
                "estimated_cost": candidate.get("avg_cost"),
                "planned_start": gen_item.planned_start,
                "estimated_duration_min": gen_item.estimated_duration_min,
                "sequence_order": seq,
                "source": "ai",
                "notes": gen_item.notes,
            }
        )
    return items


async def generate_itinerary(
    trip_id: str, user_id: str, request: ItineraryGenerateRequest
) -> tuple[dict[str, Any], bool]:
    """Returns (response_payload_dict, degraded). Raises NotFoundError /
    ForbiddenError / BusinessRuleError (CLARIFICATION_NEEDED) per
    API_SPECIFICATION.md §4."""
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")

    destination = request.destination or trip["destination"]
    budget = request.budget or (float(trip["budget_planned"]) if trip["budget_planned"] else None)
    start_date = request.time_window.start if request.time_window else trip["start_date"]
    end_date = request.time_window.end if request.time_window else trip["end_date"]

    missing = [
        name
        for name, value in [("destination", destination), ("budget", budget), ("dates", start_date)]
        if not value
    ]
    if missing:
        raise BusinessRuleError(
            "CLARIFICATION_NEEDED",
            _clarification_question(missing),
            details={"missing_fields": missing},
        )

    day_count = max(1, (end_date - start_date).days + 1) if end_date else 1
    day_count = min(day_count, _MAX_DAYS)
    day_dates = _day_dates(start_date, day_count)

    context = await _load_context(user_id)
    candidates = await _get_candidates(destination)

    own_ideas_text = None
    if request.use_own_ideas:
        notes = await trips_repo.list_notes(trip_id)
        own_ideas_text = "\n".join(n["raw_text"] for n in notes) or None

    gateway = get_llm_gateway()
    degraded = False
    items: list[dict[str, Any]]
    summary = f"Here's a starter plan for {destination}."

    if gateway is None or not candidates:
        degraded = gateway is None
        items = _build_fallback_itinerary(candidates, day_count)
    else:
        try:
            response = await gateway.complete(
                [
                    LLMMessage(MessageRole.SYSTEM, itinerary_prompts.SYSTEM_PROMPT),
                    LLMMessage(
                        MessageRole.USER,
                        itinerary_prompts.build_user_message(
                            destination=destination,
                            start_date=start_date.isoformat(),
                            end_date=(end_date or start_date).isoformat(),
                            day_count=day_count,
                            budget=budget,
                            budget_currency=trip["budget_currency"],
                            interests=request.interests or context["interest_labels"],
                            travel_style=context["profile"].get("travel_style"),
                            pace=context["profile"].get("pace"),
                            candidates=candidates,
                            own_ideas_text=own_ideas_text,
                        ),
                    ),
                ],
                response_schema=_GeneratedItinerary,
                config=GenerationConfig(
                    temperature=0.6, max_output_tokens=4096, timeout_seconds=25.0
                ),
            )
            assert isinstance(response.parsed, _GeneratedItinerary)
            items = _map_generated_items(response.parsed, candidates)
            if not items:
                degraded = True
                items = _build_fallback_itinerary(candidates, day_count)
            else:
                summary = response.parsed.summary
        except LLMProviderError:
            logger.warning("itinerary_generation_llm_failed", exc_info=True)
            degraded = True
            items = _build_fallback_itinerary(candidates, day_count)

    for item in items:
        item["planned_end"] = business_rules.compute_planned_end(
            item["planned_start"], item["estimated_duration_min"]
        )

    budget_summary, conflicts = await business_rules.validate_itinerary(items, day_dates, budget)

    days_payload = [
        {"day_number": n, "date": day_dates[n], "items": [i for i in items if i["day_number"] == n]}
        for n in range(1, day_count + 1)
    ]
    await trips_repo.replace_itinerary(trip_id, days_payload)

    generation_status = "fallback_used" if degraded else "succeeded"
    await trips_repo.set_generation_status(trip_id, generation_status)
    await trips_repo.update_trip(
        trip_id,
        **{
            k: v
            for k, v in {
                "start_date": start_date if not trip["start_date"] else None,
                "end_date": end_date if not trip["end_date"] else None,
                "budget_planned": budget if not trip["budget_planned"] else None,
            }.items()
            if v is not None
        },
    )

    saved_days = await trips_repo.get_itinerary(trip_id)
    await analytics_service.track(
        user_id,
        "itinerary_generated",
        {"trip_id": trip_id, "degraded": degraded, "item_count": len(items)},
    )
    return (
        {
            "trip_id": trip_id,
            "generation_status": generation_status,
            "summary": summary,
            "days": saved_days,
            "budget_summary": budget_summary,
            "conflicts": conflicts,
        },
        degraded,
    )


def _clarification_question(missing: list[str]) -> str:
    if "destination" in missing:
        return "Where would you like to go?"
    if "dates" in missing:
        return "What dates are you planning to travel?"
    if "budget" in missing:
        return "What's your rough budget for this trip?"
    return "A few more details are needed to plan this trip."
