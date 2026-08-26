"""Request/response schemas for /v1/heritage/* — F8/F9
(API_SPECIFICATION.md §7/§8)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

HeritageLayer = Literal["overview", "deep"]
Confidence = Literal["high", "low"]


class NarrationQuery(BaseModel):
    layer: HeritageLayer = "overview"
    section: str | None = Field(default=None, max_length=200)


class NarrationResponse(BaseModel):
    poi_id: str
    poi_name: str
    layer: HeritageLayer
    narration: str
    confidence: Confidence
    sources: list[str]


class PhotoQaResponse(BaseModel):
    poi_id: str | None
    answer: str
    confidence: Confidence
    grounded: bool
