"""
Request/response schemas for /v1/onboarding/* — see docs/API_SPECIFICATION.md
§3 and IMPLEMENTATION_BLUEPRINT.md F2 (BR-019, FR-003).

RESOLVED AMBIGUITY (CLAUDE.md §13 — documented, not silent): the PRD's FR-003
"Inputs" row lists four distinct onboarding inputs — interests, travel style,
pace, budget bracket — matching `profiles.travel_style`/`profiles.pace`/
`profiles.budget_bracket` (DATABASE_SCHEMA.md §3) and this request body's four
fields exactly. Neither the PRD nor the engineering docs enumerate concrete
values for `travel_style` (unlike `pace`, which has an explicit DB CHECK
constraint: relaxed/balanced/packed) or `budget_bracket` (DATABASE_SCHEMA.md's
column comment gives "e.g. budget/mid/premium" as an example). This module
fixes concrete, documented enums for both:
  - `budget_bracket`: budget/mid/premium — taken directly from the schema
    comment's own example, the least ambiguous option available.
  - `travel_style`: planned/flexible/spontaneous — a "how much structure do
    you want in your itinerary" axis, deliberately distinct from `pace`
    (day-to-day busyness) and from `interests` (topic preferences) so the
    three onboarding questions don't overlap or duplicate each other. This is
    a genuine product decision made in the absence of a documented one, not
    an invented requirement — it fills an acceptance-criteria-relevant gap
    (a value is required for the column to be usable by the future
    Personalization Engine, AI_ARCHITECTURE.md §7) without changing what the
    PRD actually asks for (a short travel-style preference captured at
    onboarding).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TravelStyle = Literal["planned", "flexible", "spontaneous"]
Pace = Literal["relaxed", "balanced", "packed"]
BudgetBracket = Literal["budget", "mid", "premium"]
# Final Personalization phase — two new onboarding questions, bringing the
# total from 4 to 6 (interests, travel_style, pace, budget_bracket,
# travel_companion, trip_motivation), per this phase's explicit "5-6
# meaningful questions" target. Same pattern as the existing three enums:
# a small, documented, non-overlapping value set.
TravelCompanion = Literal["solo", "family", "friends", "couple", "flexible"]


class InterestResponse(BaseModel):
    id: int
    slug: str
    label: str


class OnboardingResponsesRequest(BaseModel):
    """All fields are optional so the same endpoint serves both a completed
    onboarding submission and the FR-003 "skip" alternative flow (whatever
    was answered before skipping, including nothing at all, is saved) —
    see docs/API_SPECIFICATION.md §3 and onboarding_service.py."""

    interest_ids: list[int] = Field(default_factory=list)
    travel_style: TravelStyle | None = None
    pace: Pace | None = None
    budget_bracket: BudgetBracket | None = None
    travel_companion: TravelCompanion | None = None
    # Free text — deliberately NOT constrained to a fixed enum (the PRD's
    # own "conversational question" intent). Capped to match the DB
    # CHECK constraint (migration 20260828120003) — a generous limit for
    # "what makes a trip special for you?", not a full essay field.
    trip_motivation: str | None = Field(default=None, max_length=500)


class OnboardingResponseData(BaseModel):
    onboarding_completed: bool
    onboarding_completed_at: datetime | None
    interest_ids: list[int]
    travel_style: str | None
    pace: str | None
    budget_bracket: str | None
    travel_companion: str | None
    trip_motivation: str | None


class OnboardingStatusResponse(BaseModel):
    onboarding_completed: bool
    onboarding_completed_at: datetime | None
