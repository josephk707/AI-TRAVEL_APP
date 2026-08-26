"""Request/response schemas for /v1/trips/{id}/location/* — F7
(API_SPECIFICATION.md §6)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LocationConsentRequest(BaseModel):
    consent: bool


class LocationPingRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    recorded_at: datetime | None = None


class ManualLocationRequest(BaseModel):
    poi_id: str


class ArrivalEvent(BaseModel):
    itinerary_item_id: str
    poi_name: str


class NearbyPoi(BaseModel):
    poi_id: str
    name: str
    distance_m: float


class LocationPingResponse(BaseModel):
    arrival_event: ArrivalEvent | None
    nearby: list[NearbyPoi]
