"""
F3 — AI Conversational Planner & Personalised Itinerary Generation
(IMPLEMENTATION_BLUEPRINT.md F3, AI_ARCHITECTURE.md §2, API_SPECIFICATION.md §4).

Pipeline, matching AI_ARCHITECTURE.md §2 (AI-first itinerary phase,
2026-09-06 — documented decision, CLAUDE.md §13):
  1. Assemble context (profile + interests, request payload, own notes,
     personalization summary)
  2. Known-place retrieval from the `pois` catalog — now an OPTIONAL hint
     list handed to the model, no longer the only places it may use
  3. LLM composition (Gemini, structured output): the model plans from its
     own knowledge of real places in the destination, tailored to budget,
     interests, dates and pace, returning name / area / category /
     approximate coordinates / cost / why-it-fits per stop, or — when it
     does not recognise the destination — a clarification question and no
     plan (prompts/itinerary.py)
  3b. Grounding (place_grounding_service.py): every proposed stop is
     resolved to a catalog row, a live-geocoded and cached place, the
     model's own estimate, or "unresolved" — each labelled, never trusted
     blindly (CLAUDE.md §8)
  4. Business-rule validation (app/services/business_rules.py) — deterministic
  5. Persist trips/itinerary_days/itinerary_items; set generation_status;
     store the destination centre on the trip when it was unknown
  6. Return to client

Failure handling (FR-001 exception flow): any LLM failure — not configured,
timeout, malformed output — serves the deterministic fallback scheduler
(`_build_fallback_itinerary`, real catalog POIs only, no AI call, no
fabrication) and sets `generation_status='fallback_used'` with
`meta.degraded_mode=True`. This is a hard requirement (CLAUDE.md §3), not
an optimization.

Unknown destination (product-owner requirement, this phase): the model is
told to refuse to plan for a place it cannot identify. That comes back as
`CLARIFICATION_NEEDED` with `missing_fields=["destination"]` and the
model's own follow-up question — the client re-asks for the destination
rather than ever showing a plan for a place nobody recognises.
"""

from __future__ import annotations

import logging
import re
from datetime import date as date_cls
from datetime import timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.exceptions import BusinessRuleError, ForbiddenError, NotFoundError
from app.repositories.ai_conversations_repository import AiConversationsRepository
from app.repositories.interests_repository import InterestsRepository
from app.repositories.onboarding_repository import OnboardingRepository
from app.repositories.pois_repository import PoisRepository
from app.repositories.profiles_repository import ProfilesRepository
from app.repositories.trips_repository import TripsRepository
from app.schemas.trips import ItineraryGenerateRequest
from app.services import analytics_service, business_rules, personalization_service
from app.services.ai.factory import get_llm_gateway
from app.services.ai.language import language_instruction
from app.services.ai.llm_gateway import GenerationConfig, LLMMessage, LLMProviderError, MessageRole
from app.services.ai.prompts import itinerary as itinerary_prompts
from app.services.place_grounding_service import (
    PlaceGrounder,
    ProposedPlace,
    get_geocoder,
    resolve_destination_centre,
)

logger = logging.getLogger("app.services.itinerary")

_MAX_CANDIDATES = 30
_MAX_DAYS = 21
_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{1,2})\b")

PlaceCategory = Literal["heritage", "restaurant", "attraction", "nature", "shopping", "other"]


class _GeneratedItem(BaseModel):
    """One stop as the model returns it. Either `candidate_index` (a KNOWN
    PLACES entry) or `place_name` (a real place from the model's own
    knowledge) identifies the place; the rest describes the visit."""

    day_number: int = Field(ge=1, le=_MAX_DAYS)
    candidate_index: int | None = Field(
        default=None, ge=0, description="Index into KNOWN PLACES, if reusing one of them."
    )
    place_name: str | None = Field(
        default=None, max_length=200, description="Commonly used name of a real place."
    )
    area: str | None = Field(default=None, max_length=200, description="Neighbourhood / locality.")
    category: PlaceCategory | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    planned_start: str = Field(description='24-hour "HH:MM".')
    estimated_duration_min: int = Field(ge=15, le=600)
    estimated_cost: float | None = Field(
        default=None, ge=0, description="Per-person cost in the trip currency; 0 if free."
    )
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("planned_start")
    @classmethod
    def _normalize_time(cls, value: str) -> str:
        match = _TIME_RE.match(value or "")
        if not match:
            raise ValueError("planned_start must be HH:MM")
        hour, minute = int(match.group(1)), int(match.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("planned_start must be a valid 24-hour time")
        return f"{hour:02d}:{minute:02d}"


class _GeneratedItinerary(BaseModel):
    destination_recognized: bool = Field(
        default=True, description="False when the destination cannot be identified."
    )
    clarification_question: str | None = Field(
        default=None, description="Asked only when destination_recognized is false."
    )
    summary: str
    destination_lat: float | None = Field(default=None, ge=-90, le=90)
    destination_lng: float | None = Field(default=None, ge=-180, le=180)
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


def _candidate_item_fields(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "poi_id": str(candidate["id"]),
        "poi_name": candidate["name"],
        "poi_lat": candidate["lat"],
        "poi_lng": candidate["lng"],
        "poi_category": candidate["category"],
        "poi_opening_hours": candidate.get("opening_hours"),
        "poi_avg_cost": candidate.get("avg_cost"),
        "place_name": candidate["name"],
        "place_area": None,
        "place_category": candidate["category"],
        "place_lat": candidate["lat"],
        "place_lng": candidate["lng"],
        "location_source": "poi",
    }


def _build_fallback_itinerary(
    candidates: list[dict[str, Any]], day_count: int
) -> list[dict[str, Any]]:
    """The pre-authored, non-AI fallback (AI_ARCHITECTURE.md §2 "Failure
    handling"): a deterministic greedy scheduler over REAL catalog POIs
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
            items.append(
                {
                    **_candidate_item_fields(candidate),
                    "day_number": day_number,
                    "estimated_cost": candidate.get("avg_cost"),
                    "planned_start": start_slots[slot_index % len(start_slots)],
                    "estimated_duration_min": 120,
                    "sequence_order": slot_index,
                    "source": "ai",
                    "notes": None,
                }
            )
    return items


async def _ground_generated_items(
    generated: _GeneratedItinerary,
    candidates: list[dict[str, Any]],
    grounder: PlaceGrounder,
) -> list[dict[str, Any]]:
    """Turns the model's stops into persistable items. A valid
    `candidate_index` maps straight to that catalog row; anything else is
    grounded (catalog match -> geocode -> model estimate -> unresolved).
    A stop that names nothing usable is dropped with a warning, never
    persisted as a blank row."""
    resolved: list[tuple[_GeneratedItem, dict[str, Any]]] = []
    pending: list[tuple[_GeneratedItem, ProposedPlace]] = []

    for gen_item in generated.items:
        index = gen_item.candidate_index
        if index is not None and 0 <= index < len(candidates):
            resolved.append((gen_item, _candidate_item_fields(candidates[index])))
            continue
        if index is not None:
            logger.warning(
                "itinerary_generation_hallucinated_index_rejected",
                extra={"candidate_index": index},
            )
        name = (gen_item.place_name or "").strip()
        if not name:
            continue
        pending.append(
            (
                gen_item,
                ProposedPlace(
                    name=name,
                    area=gen_item.area,
                    category=gen_item.category,
                    lat=gen_item.lat,
                    lng=gen_item.lng,
                ),
            )
        )

    grounded = await grounder.ground_many([place for _, place in pending])
    for (gen_item, _), place in zip(pending, grounded, strict=True):
        resolved.append((gen_item, place.as_item_fields()))

    # Restore the model's own ordering (candidate items were collected
    # first), then order each day by start time so sequence_order is honest.
    order = {id(gen_item): position for position, gen_item in enumerate(generated.items)}
    resolved.sort(key=lambda pair: order[id(pair[0])])

    items: list[dict[str, Any]] = []
    for gen_item, fields in resolved:
        cost = gen_item.estimated_cost
        if cost is None and fields.get("poi_avg_cost") is not None:
            cost = float(fields["poi_avg_cost"])
        items.append(
            {
                **fields,
                "day_number": gen_item.day_number,
                "estimated_cost": cost,
                "planned_start": gen_item.planned_start,
                "estimated_duration_min": gen_item.estimated_duration_min,
                "source": "ai",
                "notes": gen_item.notes,
            }
        )

    items.sort(
        key=lambda item: (
            item["day_number"],
            business_rules.minutes_since_midnight(item["planned_start"]) or 0,
        )
    )
    sequence: dict[int, int] = {}
    for item in items:
        seq = sequence.get(item["day_number"], 0)
        sequence[item["day_number"]] = seq + 1
        item["sequence_order"] = seq
    return items


def _grounding_stats(items: list[dict[str, Any]]) -> dict[str, int]:
    stats: dict[str, int] = {}
    for item in items:
        key = str(item.get("location_source") or "poi")
        stats[key] = stats.get(key, 0) + 1
    return stats


async def _log_plan_to_conversation(
    user_id: str, trip_id: str, summary: str, model: str, tokens: int | None
) -> None:
    """The generated plan's summary becomes the first assistant turn of the
    trip's conversation, so the modification pipeline (which replays
    history) starts with the model's own framing of the plan. Best-effort:
    a logging failure never fails a generation the traveller already has."""
    try:
        conv_repo = AiConversationsRepository()
        conversation_id = await conv_repo.get_or_create_conversation(user_id, trip_id)
        await conv_repo.log_message(
            conversation_id, role="assistant", content=summary, model=model, tokens_used=tokens
        )
    except Exception:  # noqa: BLE001
        logger.warning("itinerary_conversation_log_failed", exc_info=True)


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
    centre: tuple[float, float] | None = None
    centre_source = "unresolved"
    model_name = ""
    output_tokens: int | None = None

    if gateway is None:
        degraded = True
        items = _build_fallback_itinerary(candidates, day_count)
        if not items:
            summary = (
                f"Live planning is temporarily unavailable and we don't have saved places "
                f"for {destination} yet — please try again shortly."
            )
    else:
        try:
            preferred_language = context["profile"].get("preferred_language")
            system_prompt = itinerary_prompts.SYSTEM_PROMPT + language_instruction(
                str(preferred_language) if preferred_language else None
            )
            # Final Personalization phase — a short, real, previously-computed
            # summary of this exact traveller (never a second AI call on this
            # hot path; see personalization_service.get_personalization_context's
            # own docstring). None for a user who has never opened their Travel
            # DNA screen — itinerary generation degrades to its pre-existing
            # behavior exactly as before this phase.
            personalization_summary = await personalization_service.get_personalization_context(
                user_id
            )
            response = await gateway.complete(
                [
                    LLMMessage(MessageRole.SYSTEM, system_prompt),
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
                            personalization_summary=personalization_summary,
                        ),
                    ),
                ],
                response_schema=_GeneratedItinerary,
                config=GenerationConfig(
                    temperature=0.6, max_output_tokens=8192, timeout_seconds=45.0
                ),
            )
            assert isinstance(response.parsed, _GeneratedItinerary)
            generated = response.parsed
            model_name = response.model
            output_tokens = response.output_tokens

            if not generated.destination_recognized:
                # FR-001 alt. flow, extended: the model does not know this
                # place — ask, never plan. Nothing is persisted.
                question = (
                    generated.clarification_question
                    or f'I don\'t know a place called "{destination}" — could you check the '
                    "spelling or tell me the city and country you mean?"
                )
                await analytics_service.track(
                    user_id,
                    "itinerary_destination_unrecognized",
                    {"trip_id": trip_id, "destination": destination},
                )
                raise BusinessRuleError(
                    "CLARIFICATION_NEEDED",
                    question,
                    details={
                        "missing_fields": ["destination"],
                        "reason": "destination_unrecognized",
                    },
                )

            geocoder = get_geocoder()
            centre, centre_source = await resolve_destination_centre(
                destination,
                known=(trip.get("destination_lat"), trip.get("destination_lng")),
                ai_estimate=(generated.destination_lat, generated.destination_lng),
                geocoder=geocoder,
            )
            grounder = PlaceGrounder(destination, centre, candidates, geocoder=geocoder)
            items = await _ground_generated_items(generated, candidates, grounder)
            if not items:
                degraded = True
                items = _build_fallback_itinerary(candidates, day_count)
            else:
                summary = generated.summary
        except LLMProviderError:
            logger.warning("itinerary_generation_llm_failed", exc_info=True)
            degraded = True
            items = _build_fallback_itinerary(candidates, day_count)

    for item in items:
        item["planned_end"] = business_rules.compute_planned_end(
            item["planned_start"], item["estimated_duration_min"]
        )

    budget_summary, conflicts = await business_rules.validate_itinerary(items, day_dates, budget)
    for item in items:
        # A stop whose location could not be verified is always something to
        # confirm on the ground, whatever its opening-hours status.
        if item.get("location_source") in ("ai_estimate", "unresolved"):
            item["verify_on_arrival"] = True

    days_payload = [
        {"day_number": n, "date": day_dates[n], "items": [i for i in items if i["day_number"] == n]}
        for n in range(1, day_count + 1)
    ]
    await trips_repo.replace_itinerary(trip_id, days_payload)

    generation_status = "fallback_used" if degraded else "succeeded"
    await trips_repo.set_generation_status(trip_id, generation_status)

    trip_updates: dict[str, Any] = {
        k: v
        for k, v in {
            "start_date": start_date if not trip["start_date"] else None,
            "end_date": end_date if not trip["end_date"] else None,
            "budget_planned": budget if not trip["budget_planned"] else None,
        }.items()
        if v is not None
    }
    if request.destination and request.destination != trip["destination"]:
        trip_updates["destination"] = request.destination
    if centre is not None and (
        trip.get("destination_lat") is None or trip.get("destination_lng") is None
    ):
        trip_updates["destination_lat"] = centre[0]
        trip_updates["destination_lng"] = centre[1]
    if trip_updates:
        await trips_repo.update_trip(trip_id, **trip_updates)

    if not degraded and summary:
        await _log_plan_to_conversation(user_id, trip_id, summary, model_name, output_tokens)

    saved_days = await trips_repo.get_itinerary(trip_id)
    await analytics_service.track(
        user_id,
        "itinerary_generated",
        {
            "trip_id": trip_id,
            "degraded": degraded,
            "item_count": len(items),
            "grounding": _grounding_stats(items),
            "centre_source": centre_source,
        },
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
