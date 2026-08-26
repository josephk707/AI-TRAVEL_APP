"""Request/response schemas for /v1/favorites, /v1/collections — F13
(API_SPECIFICATION.md §11)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FavoriteRequest(BaseModel):
    poi_id: str


class FavoriteResponse(BaseModel):
    poi_id: str
    poi_name: str
    poi_category: str
    created_at: datetime


class CollectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CollectionResponse(BaseModel):
    id: str
    user_id: str
    name: str
    created_at: datetime
    item_count: int = 0


class CollectionItemRequest(BaseModel):
    poi_id: str


class CollectionItemResponse(BaseModel):
    poi_id: str
    poi_name: str
    poi_category: str
    added_at: datetime
