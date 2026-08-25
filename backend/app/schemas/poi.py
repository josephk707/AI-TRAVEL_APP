"""
Request/response schemas for /v1/pois/* — see docs/API_SPECIFICATION.md §5
and IMPLEMENTATION_BLUEPRINT.md F6.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

PoiCategory = Literal["heritage", "restaurant", "attraction", "nature", "shopping", "other"]


class Coordinates(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class PoiResponse(BaseModel):
    id: str
    name: str
    category: PoiCategory
    location: Coordinates
    address: str | None
    city: str | None
    region: str | None
    country: str
    opening_hours: dict[str, Any] | None
    avg_cost: float | None
    source: Literal["curated", "places_api"]
    is_heritage_flagship: bool
    created_at: datetime
    updated_at: datetime


class PoiSearchQuery(BaseModel):
    """Query params for `GET /pois/search` — at least one of `query` or a
    full `lat`/`lng` pair must be supplied (bounding-box-by-point + radius,
    per API_SPECIFICATION.md §5's "text/category/bounding box" wording)."""

    query: str | None = Field(default=None, min_length=1, max_length=200)
    category: PoiCategory | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    radius_m: float = Field(default=5000, gt=0, le=50000)

    @model_validator(mode="after")
    def _require_query_or_location(self) -> PoiSearchQuery:
        has_location = self.lat is not None and self.lng is not None
        if not self.query and not has_location:
            raise ValueError("Provide either 'query' or both 'lat' and 'lng'.")
        if (self.lat is None) != (self.lng is None):
            raise ValueError("'lat' and 'lng' must be supplied together.")
        return self


class PoiNearbyQuery(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius_m: float = Field(default=2000, gt=0, le=50000)
    category: PoiCategory | None = None
