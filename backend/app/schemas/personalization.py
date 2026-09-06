"""Response schema for GET /v1/personalization/travel-dna — Final
Personalization phase."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TravelDnaResponse(BaseModel):
    travel_style: str | None
    pace: str | None
    budget_bracket: str | None
    travel_companion: str | None
    trip_motivation: str | None
    interests: list[str]
    favorite_categories: dict[str, int]
    trips_planned: int
    places_saved: int
    travel_personality: str
    summary: str
    generated_by: str  # "ai" | "template" — honest about whether Gemini wrote this
    updated_at: datetime
