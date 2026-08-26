"""Request/response schemas for /v1/reviews, /v1/pois/{id}/reviews,
/v1/admin/reviews/* — F14 (API_SPECIFICATION.md §12/§19)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ReviewStatus = Literal["pending", "published", "rejected"]


class ReviewCreateRequest(BaseModel):
    poi_id: str
    trip_id: str
    rating: int = Field(ge=1, le=5)
    review_text: str | None = Field(default=None, max_length=2000)


class ReviewResponse(BaseModel):
    id: str
    user_id: str
    poi_id: str
    trip_id: str
    rating: int
    review_text: str | None
    status: ReviewStatus
    created_at: datetime


class ModerateReviewRequest(BaseModel):
    decision: Literal["publish", "reject"]
