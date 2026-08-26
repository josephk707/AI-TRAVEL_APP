"""Request/response schemas for /v1/trips/{id}/disruptions* — F20
(API_SPECIFICATION.md's Phase 8 addition, resolving ARCHITECTURE_REVIEW.md
H2 in favor of IMPLEMENTATION_BLUEPRINT.md F20's dedicated endpoints)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TriggerType = Literal[
    "weather",
    "closure",
    "delay",
    "off_route",
    "missed_activity",
    "budget_overrun",
    "schedule_change",
    "manual_request",
]


class DisruptionEventResponse(BaseModel):
    id: str
    trip_id: str
    itinerary_item_id: str
    trigger_type: TriggerType
    detected_at: datetime
    proposal: dict[str, Any]
    status: Literal["proposed", "accepted", "dismissed"]
    resolved_at: datetime | None


class DisruptionResolveRequest(BaseModel):
    decision: Literal["accept", "dismiss"]
    alternative_index: int | None = Field(default=None, ge=0)
