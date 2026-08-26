"""
F4 — Incorporate User-Provided Trip Ideas (IMPLEMENTATION_BLUEPRINT.md F4,
AI_ARCHITECTURE.md §3, API_SPECIFICATION.md §4 `POST /trips/{id}/notes`).

Runs before Itinerary Generation (F3), which reads `trip_raw_notes.
extracted_places` back via `use_own_ideas=true` — see itinerary_service.py.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.core.exceptions import ForbiddenError, NotFoundError
from app.repositories.pois_repository import PoisRepository
from app.repositories.trips_repository import TripsRepository
from app.services import business_rules
from app.services.ai.factory import get_llm_gateway
from app.services.ai.llm_gateway import GenerationConfig, LLMMessage, LLMProviderError, MessageRole
from app.services.ai.prompts import idea_extraction as extraction_prompts

logger = logging.getLogger("app.services.idea_extraction")

_LONG_DISTANCE_KM = 300.0


class _ExtractedIdeas(BaseModel):
    places: list[str] = Field(default_factory=list)
    dates_mentioned: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "low"


async def _match_places(place_names: list[str], destination: str) -> list[dict]:
    """Fuzzy-matches extracted place names against the real `pois` table
    scoped to this trip's destination. Unmatched names are still returned
    (matched=False) — NEVER silently dropped (FR-005 business rule)."""
    repo = PoisRepository()
    city_token = destination.split(",")[0].strip()
    matched = []
    for name in place_names:
        candidates = await repo.search_text(name, category=None, limit=5)
        # Prefer a candidate whose city also plausibly matches the trip's
        # destination — a fuzzy heuristic, not exact, since neither name
        # matching nor city matching is guaranteed precise data.
        best = next(
            (c for c in candidates if city_token.lower() in (c.get("city") or "").lower()), None
        )
        best = best or (candidates[0] if candidates else None)
        if best:
            matched.append(
                {
                    "name": name,
                    "matched": True,
                    "poi_id": str(best["id"]),
                    "poi_name": best["name"],
                    "lat": best["lat"],
                    "lng": best["lng"],
                    "city": best.get("city"),
                }
            )
        else:
            matched.append({"name": name, "matched": False, "poi_id": None})
    return matched


def _compute_unparsed_remainder(raw_text: str, extracted: _ExtractedIdeas) -> str | None:
    remainder = raw_text
    for span in [*extracted.places, *extracted.activities]:
        if span and span.lower() in remainder.lower():
            idx = remainder.lower().find(span.lower())
            remainder = remainder[:idx] + remainder[idx + len(span) :]
    remainder = " ".join(remainder.split())
    return remainder or None


def _detect_conflicts(matched_places: list[dict]) -> list[str]:
    located = [p for p in matched_places if p.get("matched") and p.get("lat") is not None]
    conflicts = []
    for i, a in enumerate(located):
        for b in located[i + 1 :]:
            if a.get("city") and b.get("city") and a["city"] != b["city"]:
                distance = business_rules.haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
                if distance > _LONG_DISTANCE_KM:
                    conflicts.append(
                        f"'{a['poi_name']}' and '{b['poi_name']}' are {distance:.0f} km apart "
                        "(different cities) — combining them in the same short trip may need "
                        "extra travel time. Consider spreading them across more days."
                    )
    return conflicts


async def extract_ideas(trip_id: str, user_id: str, raw_text: str) -> tuple[dict, list[str]]:
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")

    note = await trips_repo.create_note(trip_id, user_id, raw_text)

    gateway = get_llm_gateway()
    if gateway is None:
        # Nothing extractable without a provider — the raw note is still
        # preserved (already persisted above) and passed forward as-is to
        # F3, never discarded (FR-005 alt. flow).
        return note, []

    try:
        response = await gateway.complete(
            [
                LLMMessage(MessageRole.SYSTEM, extraction_prompts.SYSTEM_PROMPT),
                LLMMessage(MessageRole.USER, raw_text),
            ],
            response_schema=_ExtractedIdeas,
            config=GenerationConfig(temperature=0.2, max_output_tokens=1024, timeout_seconds=15.0),
        )
    except LLMProviderError:
        logger.warning("idea_extraction_llm_failed", exc_info=True)
        return note, []

    assert isinstance(response.parsed, _ExtractedIdeas)
    parsed = response.parsed
    matched_places = await _match_places(parsed.places, trip["destination"])
    unparsed_remainder = _compute_unparsed_remainder(raw_text, parsed)
    conflicts = _detect_conflicts(matched_places)

    extracted_payload = [
        {
            "name": p["name"],
            "matched": p["matched"],
            "poi_id": p.get("poi_id"),
        }
        for p in matched_places
    ] + ([{"dates_mentioned": parsed.dates_mentioned}] if parsed.dates_mentioned else [])

    await trips_repo.update_note_parsed(note["id"], extracted_payload, unparsed_remainder)
    note["extracted_places"] = extracted_payload
    note["unparsed_remainder"] = unparsed_remainder
    return note, conflicts
