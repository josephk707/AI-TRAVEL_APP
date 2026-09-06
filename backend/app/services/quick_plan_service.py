"""
F22 — Weekend/Local Outing Quick Plan (IMPLEMENTATION_BLUEPRINT.md F22,
AI_ARCHITECTURE.md §7). Deliberately scoped down from F3's full itinerary
pipeline: no heritage narration, no multi-day logistics (FR-015 business
rule) — 1-3 real candidates chosen to fit the stated time/budget/mood,
with the SAME graceful LLM-unavailable fallback (deterministic top-N
candidates, never a fabricated response) as every other AI pipeline in
this codebase.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.core.exceptions import AppError, NotFoundError
from app.repositories.collections_repository import CollectionsRepository
from app.repositories.pois_repository import PoisRepository
from app.repositories.profiles_repository import ProfilesRepository
from app.repositories.quick_plan_repository import QuickPlanRepository
from app.services.ai.factory import get_llm_gateway
from app.services.ai.language import language_instruction
from app.services.ai.llm_gateway import GenerationConfig, LLMMessage, LLMProviderError, MessageRole
from app.services.ai.prompts import quick_plan as quick_plan_prompts

logger = logging.getLogger("app.services.quick_plan")

_MAX_STOPS = 3
_MIN_PER_STOP_MIN = 60


class _QuickPlanItem(BaseModel):
    candidate_index: int = Field(ge=0)
    sequence_order: int = Field(ge=0)


class _QuickPlanSelection(BaseModel):
    summary: str
    items: list[_QuickPlanItem] = Field(default_factory=list)


def _max_stops_for(time_available_min: int) -> int:
    return max(1, min(_MAX_STOPS, time_available_min // _MIN_PER_STOP_MIN))


def _fallback_selection(candidates: list[dict], max_stops: int) -> _QuickPlanSelection:
    items = [
        _QuickPlanItem(candidate_index=i, sequence_order=i)
        for i in range(min(max_stops, len(candidates)))
    ]
    return _QuickPlanSelection(
        summary="Here's a quick outing based on nearby favorites.", items=items
    )


async def generate_quick_plan(
    user_id: str,
    time_available_min: int,
    budget: float | None,
    occasion: str | None,
    lat: float | None,
    lng: float | None,
) -> dict:
    profile = await ProfilesRepository().get_by_id(user_id)

    if lat is not None and lng is not None:
        candidates = await PoisRepository().search_nearby(lat, lng, 5000.0, category=None, limit=15)
    else:
        home_region = (profile or {}).get("home_region")
        candidates = (
            await PoisRepository().search_text(str(home_region), category=None, limit=15)
            if home_region
            else []
        )

    if not candidates:
        raise AppError(
            "NOT_ENOUGH_LOCAL_DATA",
            "There isn't enough local data for this area yet to build a good quick plan.",
            422,
        )

    max_stops = _max_stops_for(time_available_min)
    gateway = get_llm_gateway()

    if gateway is None:
        selection = _fallback_selection(candidates, max_stops)
    else:
        preferred_language = (profile or {}).get("preferred_language")
        system_prompt = quick_plan_prompts.SYSTEM_PROMPT + language_instruction(
            str(preferred_language) if preferred_language else None
        )
        try:
            response = await gateway.complete(
                [
                    LLMMessage(MessageRole.SYSTEM, system_prompt),
                    LLMMessage(
                        MessageRole.USER,
                        quick_plan_prompts.build_user_message(
                            time_available_min=time_available_min,
                            budget=budget,
                            occasion=occasion,
                            candidates=candidates,
                        ),
                    ),
                ],
                response_schema=_QuickPlanSelection,
                config=GenerationConfig(
                    temperature=0.6, max_output_tokens=1024, timeout_seconds=20.0
                ),
            )
            assert isinstance(response.parsed, _QuickPlanSelection)
            selection = response.parsed
            valid_items = [
                item for item in selection.items if 0 <= item.candidate_index < len(candidates)
            ]
            if not valid_items:
                selection = _fallback_selection(candidates, max_stops)
            else:
                selection = _QuickPlanSelection(
                    summary=selection.summary, items=valid_items[:max_stops]
                )
        except LLMProviderError:
            logger.warning("quick_plan_llm_failed", exc_info=True)
            selection = _fallback_selection(candidates, max_stops)

    repo = QuickPlanRepository()
    plan = await repo.create_plan(user_id, time_available_min, budget, occasion)
    plan_id = str(plan["id"])
    items_to_persist = [
        {
            "poi_id": str(candidates[item.candidate_index]["id"]),
            "sequence_order": item.sequence_order,
        }
        for item in selection.items
    ]
    await repo.add_items(plan_id, items_to_persist)
    saved_items = [dict(i, poi_id=str(i["poi_id"])) for i in await repo.list_items(plan_id)]

    return {**plan, "summary": selection.summary, "items": saved_items}


async def save_to_collection(quick_plan_id: str, user_id: str) -> dict:
    repo = QuickPlanRepository()
    plan = await repo.get_plan(quick_plan_id, user_id)
    if plan is None:
        raise NotFoundError("This quick plan could not be found.")

    items = await repo.list_items(quick_plan_id)
    if not items:
        raise AppError("EMPTY_QUICK_PLAN", "This quick plan has no stops to save.", 422)

    collections_repo = CollectionsRepository()
    name = f"Quick plan — {plan['occasion'] or plan['generated_at'].strftime('%d %b %Y')}"
    collection = await collections_repo.create_collection(user_id, name)
    for item in items:
        await collections_repo.add_item(str(collection["id"]), str(item["poi_id"]))

    return {
        "collection_id": str(collection["id"]),
        "collection_name": collection["name"],
        "item_count": len(items),
    }
