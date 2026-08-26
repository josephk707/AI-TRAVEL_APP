"""Request/response schemas for /v1/quick-plans* — F22
(API_SPECIFICATION.md §18)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class QuickPlanCreateRequest(BaseModel):
    time_available_min: int = Field(ge=15, le=720)
    budget: float | None = Field(default=None, gt=0)
    occasion: str | None = Field(default=None, max_length=100)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class QuickPlanItemResponse(BaseModel):
    poi_id: str
    poi_name: str
    poi_category: str
    sequence_order: int


class QuickPlanResponse(BaseModel):
    id: str
    user_id: str
    time_available_min: int | None
    budget: float | None
    occasion: str | None
    summary: str
    generated_at: datetime
    items: list[QuickPlanItemResponse]


class SaveToCollectionResponse(BaseModel):
    collection_id: str
    collection_name: str
    item_count: int
