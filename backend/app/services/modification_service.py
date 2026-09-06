"""
F5 — Conversational Itinerary Modification (IMPLEMENTATION_BLUEPRINT.md F5,
AI_ARCHITECTURE.md §4, API_SPECIFICATION.md §4
`POST /trips/{id}/itinerary/modify`).

The model produces a SCOPED DIFF (which items change), never a full
itinerary regeneration — this is the mechanism, not just a prompt
instruction, that guarantees "only the relevant segment changes, rest of
plan preserved" (FR-004 acceptance criteria): unmentioned items are never
touched by this code path at all.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.exceptions import ForbiddenError, NotFoundError
from app.repositories.ai_conversations_repository import (
    AiConversationsRepository,
    FeedbackRepository,
)
from app.repositories.interests_repository import InterestsRepository
from app.repositories.onboarding_repository import OnboardingRepository
from app.repositories.pois_repository import PoisRepository
from app.repositories.profiles_repository import ProfilesRepository
from app.repositories.trips_repository import TripsRepository
from app.services import business_rules
from app.services.ai.factory import get_llm_gateway
from app.services.ai.language import language_instruction
from app.services.ai.llm_gateway import GenerationConfig, LLMMessage, LLMProviderError, MessageRole
from app.services.ai.prompts import modification as modification_prompts

logger = logging.getLogger("app.services.modification")

# AI_ARCHITECTURE.md §4 step 1 requires this pipeline to load the trip's
# `ai_conversations` history for multi-turn context. Capped rather than
# unbounded: only the recent turns are needed to resolve a follow-up, and
# an ever-growing transcript would push both latency and token cost up on
# every subsequent message (AI_ARCHITECTURE.md §12 cost controls).
_MAX_HISTORY_MESSAGES = 10


class _ItemChange(BaseModel):
    item_id: str | None = None
    candidate_index: int | None = None
    day_number: int | None = None
    planned_start: str | None = None
    estimated_duration_min: int | None = None
    status: Literal["planned", "confirmed", "skipped", "completed"] | None = None
    notes: str | None = None


class _ModificationResult(BaseModel):
    reply: str
    clarification_needed: bool = False
    clarification_question: str | None = None
    changes: list[_ItemChange] = Field(default_factory=list)


def _flatten_current_items(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flat = []
    for day in days:
        for item in day["items"]:
            item = dict(item)
            item["day_number"] = day["day_number"]
            flat.append(item)
    return flat


async def _load_traveller_context(user_id: str) -> tuple[dict[str, Any], list[str]]:
    """Reads ONLY the traveller attributes this pipeline actually needs to
    resolve a modification request — onboarding interests, travel style and
    pace (CLAUDE.md §8: "AI calls must receive only the context necessary
    for the task"). Deliberately narrower than
    `itinerary_service._load_context`, which additionally pulls a computed
    personalization summary for full-plan generation; a scoped diff does
    not need it. Always scoped to the authenticated `user_id`, so no other
    traveller's preferences can enter this prompt."""
    profile = await ProfilesRepository().get_by_id(user_id) or {}
    interest_ids = await OnboardingRepository().get_interest_ids_for_profile(user_id)
    all_interests = {i["id"]: i["label"] for i in await InterestsRepository().list_interests()}
    return profile, [str(all_interests[i]) for i in interest_ids if i in all_interests]


def _build_profile_block(profile: dict[str, Any], interest_labels: list[str]) -> str:
    """Real, live-testing-discovered gap (Gemini certification pass): the
    modification prompt previously received the itinerary and the candidate
    list but NOTHING about the traveller, so an entirely reasonable request
    like "add one historical place that matches my interests" was
    unanswerable — the model could only fall back to rule 3 and ask a
    clarifying question, every single time. Verified directly against the
    real Gemini API: identical prompt, identical itinerary, the only
    difference being this block, moved the response from
    `clarification_needed=true, 0 changes` to a correct scoped diff adding
    Agra Fort. Omitted entirely (not emitted as empty placeholders) when
    the profile carries none of these fields, so a brand-new traveller
    degrades to exactly the previous behavior."""
    lines = []
    if interest_labels:
        lines.append(f"interests: {', '.join(interest_labels)}")
    if profile.get("travel_style"):
        lines.append(f"travel style: {profile['travel_style']}")
    if profile.get("pace"):
        lines.append(f"preferred pace: {profile['pace']}")
    if not lines:
        return ""
    return "TRAVELLER PROFILE:\n" + "\n".join(lines) + "\n\n"


def _build_context_message(days: list[dict[str, Any]], candidates: list[dict], message: str) -> str:
    current_lines = []
    for day in days:
        for item in day["items"]:
            current_lines.append(
                f"item_id={item['id']} day={day['day_number']} "
                f"place='{item.get('poi_name') or 'unassigned'}' "
                f"start={item.get('planned_start')} end={item.get('planned_end')} "
                f"status={item.get('status')}"
            )
    candidate_lines = [f"{i}. {c['name']} ({c['category']})" for i, c in enumerate(candidates)]
    return (
        "CURRENT ITINERARY:\n"
        + "\n".join(current_lines or ["(empty)"])
        + "\n\nCANDIDATE PLACE LIST (for adding new stops only):\n"
        + "\n".join(candidate_lines or ["(none)"])
        + f"\n\nTraveller's request: {message}"
    )


async def modify_itinerary(trip_id: str, user_id: str, message: str) -> dict[str, Any]:
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")

    conv_repo = AiConversationsRepository()
    conversation_id = await conv_repo.get_or_create_conversation(user_id, trip_id)
    # Read the prior turns BEFORE logging the current one, so this request's
    # own message is not replayed back to the model as if it were history.
    history = await conv_repo.get_recent_messages(conversation_id, limit=_MAX_HISTORY_MESSAGES)
    await conv_repo.log_message(conversation_id, role="user", content=message)

    days = await trips_repo.get_itinerary(trip_id)
    candidates = await PoisRepository().search_text(
        trip["destination"].split(",")[0].strip(), category=None, limit=15
    )

    gateway = get_llm_gateway()
    if gateway is None:
        reply = (
            "Live conversational planning is temporarily unavailable, so I can't make that "
            "change right now — please try again shortly."
        )
        await conv_repo.log_message(conversation_id, role="assistant", content=reply)
        return {"reply": reply, "changed_item_ids": [], "days": days}

    profile, interest_labels = await _load_traveller_context(user_id)
    raw_language = profile.get("preferred_language")
    system_prompt = modification_prompts.SYSTEM_PROMPT + language_instruction(
        str(raw_language) if raw_language else None
    )

    # Prior turns are replayed as real conversation messages (not flattened
    # into the context blob) so the model can see that IT asked the
    # clarifying question the traveller is now answering. Only the two
    # conversational roles are replayed — a stored row with any other role
    # is skipped rather than guessed at.
    history_messages = [
        LLMMessage(MessageRole(row["role"]), str(row["content"]))
        for row in history
        if row.get("role") in (MessageRole.USER, MessageRole.ASSISTANT) and row.get("content")
    ]
    # The history window is the last N rows, so it can begin mid-exchange
    # with an assistant turn — a conversation that opens with a model turn
    # is rejected by the provider, so drop any leading assistant messages.
    while history_messages and history_messages[0].role is MessageRole.ASSISTANT:
        history_messages.pop(0)

    try:
        response = await gateway.complete(
            [
                LLMMessage(MessageRole.SYSTEM, system_prompt),
                *history_messages,
                LLMMessage(
                    MessageRole.USER,
                    _build_profile_block(profile, interest_labels)
                    + _build_context_message(days, candidates, message),
                ),
            ],
            response_schema=_ModificationResult,
            config=GenerationConfig(temperature=0.4, max_output_tokens=2048, timeout_seconds=20.0),
        )
    except LLMProviderError:
        logger.warning("itinerary_modification_llm_failed", exc_info=True)
        reply = "I couldn't process that change just now — please try again in a moment."
        await conv_repo.log_message(conversation_id, role="assistant", content=reply)
        return {"reply": reply, "changed_item_ids": [], "days": days}

    assert isinstance(response.parsed, _ModificationResult)
    result = response.parsed

    if result.clarification_needed:
        reply = result.clarification_question or "Could you clarify what you'd like to change?"
        await conv_repo.log_message(conversation_id, role="assistant", content=reply)
        return {"reply": reply, "changed_item_ids": [], "days": days}

    current_by_id = {item["id"]: item for item in _flatten_current_items(days)}
    changed_item_ids: list[str] = []
    rejected_notes: list[str] = []
    feedback_repo = FeedbackRepository()

    for change in result.changes:
        if change.item_id is not None:
            existing = current_by_id.get(uuid_str_to_key(change.item_id, current_by_id))
            if existing is None:
                continue
            proposed = dict(existing)
            if change.planned_start:
                proposed["planned_start"] = change.planned_start
            if change.estimated_duration_min:
                proposed["estimated_duration_min"] = change.estimated_duration_min
            if change.planned_start or change.estimated_duration_min:
                proposed["planned_end"] = business_rules.compute_planned_end(
                    proposed["planned_start"], proposed["estimated_duration_min"]
                )
            if change.status:
                proposed["status"] = change.status
            if change.notes:
                proposed["notes"] = change.notes

            if _introduces_new_conflict(days, existing, proposed):
                rejected_notes.append(
                    f"Keeping '{existing.get('poi_name')}' as-is — that change would create a "
                    "scheduling conflict with a nearby stop."
                )
                continue

            update_fields = {
                k: proposed[k]
                for k in (
                    "planned_start",
                    "planned_end",
                    "estimated_duration_min",
                    "status",
                    "notes",
                )
                if proposed.get(k) != existing.get(k)
            }
            if update_fields:
                await trips_repo.update_item(str(existing["id"]), trip_id, **update_fields)
                changed_item_ids.append(str(existing["id"]))
                if existing.get("source") == "ai" and change.status == "skipped":
                    await feedback_repo.log_signal(
                        user_id,
                        trip_id=trip_id,
                        itinerary_item_id=str(existing["id"]),
                        signal_type="explicit_correction",
                        value={"action": "removed_ai_suggestion"},
                    )
        elif change.candidate_index is not None and change.day_number is not None:
            if change.candidate_index < 0 or change.candidate_index >= len(candidates):
                continue
            candidate = candidates[change.candidate_index]
            duration = change.estimated_duration_min or 120
            planned_start = change.planned_start or "10:00"
            new_item = await trips_repo.insert_item(
                trip_id,
                change.day_number,
                poi_id=str(candidate["id"]),
                planned_start=planned_start,
                planned_end=business_rules.compute_planned_end(planned_start, duration),
                estimated_duration_min=duration,
                estimated_cost=candidate.get("avg_cost"),
                source="ai",
                notes=change.notes,
                sequence_order=1000,
            )
            changed_item_ids.append(str(new_item["id"]))

    reply = result.reply
    if rejected_notes:
        reply = reply + " " + " ".join(rejected_notes)
    await conv_repo.log_message(
        conversation_id,
        role="assistant",
        content=reply,
        model=response.model,
        tokens_used=response.output_tokens,
    )

    updated_days = await trips_repo.get_itinerary(trip_id)
    return {"reply": reply, "changed_item_ids": changed_item_ids, "days": updated_days}


def uuid_str_to_key(item_id: str, current_by_id: dict) -> Any:
    """The dict returned by asyncpg carries `id` as a real `uuid.UUID`
    object as the key (from the SELECT), while the model's `item_id` is a
    plain string (from the LLM's JSON output) — this normalizes the lookup
    without forcing every call site to convert both directions."""
    for key in current_by_id:
        if str(key) == item_id:
            return key
    return item_id


def _introduces_new_conflict(
    days: list[dict[str, Any]], existing: dict[str, Any], proposed: dict[str, Any]
) -> bool:
    """Builds the day's item list with `existing` swapped for `proposed`,
    then checks whether a NEW overlap/travel-time conflict appears that
    wasn't present before — the deterministic validator, not the LLM, is
    the source of truth for "is this allowed" (AI_ARCHITECTURE.md §4 step
    3-4)."""
    day = next(
        (
            d
            for d in days
            if d["day_number"] == existing.get("day_number")
            or any(i["id"] == existing["id"] for i in d["items"])
        ),
        None,
    )
    if day is None:
        return False
    before_items = [dict(i) for i in day["items"]]
    after_items = [proposed if i["id"] == existing["id"] else dict(i) for i in day["items"]]

    # Sort by parsed minutes, never by the raw value: the stored items carry
    # `datetime.time` (asyncpg) while `proposed` carries the model's "HH:MM"
    # string, and those two types are not orderable against each other —
    # this raised a real TypeError (a 500 reaching the app) as soon as a day
    # held two or more items and the traveller moved one of them.
    def _order_key(item: dict[str, Any]) -> int:
        return business_rules.minutes_since_midnight(item.get("planned_start")) or 0

    before_items.sort(key=_order_key)
    after_items.sort(key=_order_key)
    by_day_before = {day["day_number"]: before_items}
    by_day_after = {day["day_number"]: after_items}
    before_conflicts = set(
        business_rules.check_item_overlaps(by_day_before)
        + business_rules.check_travel_time_conflicts(by_day_before)
    )
    after_conflicts = set(
        business_rules.check_item_overlaps(by_day_after)
        + business_rules.check_travel_time_conflicts(by_day_after)
    )
    return len(after_conflicts - before_conflicts) > 0
