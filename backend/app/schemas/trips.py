"""
Request/response schemas for /v1/trips/* — F3/F4/F5/F12
(docs/API_SPECIFICATION.md §4, IMPLEMENTATION_BLUEPRINT.md).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

TripStatus = Literal["draft", "upcoming", "active", "completed", "cancelled"]
TripType = Literal["solo", "group", "quick_plan"]
GenerationStatus = Literal["none", "pending", "succeeded", "fallback_used", "failed"]
ItemStatus = Literal["planned", "confirmed", "skipped", "completed"]
ItemSource = Literal["ai", "user", "imported"]


class TripCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    destination: str = Field(min_length=1, max_length=200)
    destination_lat: float | None = Field(default=None, ge=-90, le=90)
    destination_lng: float | None = Field(default=None, ge=-180, le=180)
    start_date: date | None = None
    end_date: date | None = None
    budget_planned: float | None = Field(default=None, gt=0)
    budget_currency: str = Field(default="INR", min_length=3, max_length=3)

    @model_validator(mode="after")
    def _dates_in_order(self) -> TripCreateRequest:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date.")
        return self


class TripUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: TripStatus | None = None
    start_date: date | None = None
    end_date: date | None = None
    budget_planned: float | None = Field(default=None, gt=0)


class TripResponse(BaseModel):
    id: str
    owner_id: str
    title: str
    destination: str
    destination_lat: float | None
    destination_lng: float | None
    start_date: date | None
    end_date: date | None
    status: TripStatus
    trip_type: TripType
    budget_planned: float | None
    budget_currency: str
    generation_status: GenerationStatus
    created_at: datetime
    updated_at: datetime


class TripNoteCreateRequest(BaseModel):
    raw_text: str = Field(min_length=1, max_length=5000)


class TripNoteResponse(BaseModel):
    id: str
    trip_id: str
    raw_text: str
    extracted_places: list[dict] | None
    unparsed_remainder: str | None
    conflicts: list[str] = Field(default_factory=list)
    parsed_at: datetime | None
    created_at: datetime


class TimeWindow(BaseModel):
    start: date
    end: date

    @model_validator(mode="after")
    def _order(self) -> TimeWindow:
        if self.end < self.start:
            raise ValueError("time_window.end must not be before time_window.start.")
        return self


class ItineraryGenerateRequest(BaseModel):
    interests: list[str] = Field(default_factory=list)
    budget: float | None = Field(default=None, gt=0)
    time_window: TimeWindow | None = None
    destination: str | None = Field(default=None, max_length=200)
    use_own_ideas: bool = False


class ItineraryItemResponse(BaseModel):
    id: str
    poi_id: str | None
    poi_name: str | None
    sequence_order: int
    planned_start: str | None
    planned_end: str | None
    estimated_duration_min: int | None
    estimated_cost: float | None
    status: ItemStatus
    source: ItemSource
    verify_on_arrival: bool
    weather_flag: bool
    weather_alternative_suggestion: str | None
    notes: str | None


class ItineraryDayResponse(BaseModel):
    day_number: int
    date: date | None
    items: list[ItineraryItemResponse]


class BudgetSummary(BaseModel):
    estimated_total: float
    planned_budget: float | None
    over_budget: bool
    tolerance_pct: float = 10.0


class ItineraryGenerateResponse(BaseModel):
    trip_id: str
    generation_status: GenerationStatus
    summary: str
    days: list[ItineraryDayResponse]
    budget_summary: BudgetSummary | None = None
    conflicts: list[str] = Field(default_factory=list)


class ItineraryModifyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ItineraryModifyResponse(BaseModel):
    reply: str
    changed_item_ids: list[str]
    days: list[ItineraryDayResponse]


class ItineraryItemUpdateRequest(BaseModel):
    planned_start: str | None = None
    planned_end: str | None = None
    status: ItemStatus | None = None
    sequence_order: int | None = None
    notes: str | None = Field(default=None, max_length=1000)
