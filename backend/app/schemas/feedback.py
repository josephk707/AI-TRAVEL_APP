"""Request/response schemas for /v1/trips/{id}/feedback — F17
(API_SPECIFICATION.md §17)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

StopSignal = Literal["thumbs_up", "thumbs_down"]


class StopFeedback(BaseModel):
    itinerary_item_id: str
    signal: StopSignal


class TripFeedbackRequest(BaseModel):
    stops: list[StopFeedback] = Field(default_factory=list)
    free_text: str | None = Field(default=None, max_length=2000)


class TripFeedbackResponse(BaseModel):
    trip_id: str
    signals_recorded: int
