"""Request/response schemas for /v1/trips/{id}/memory-items — F11
(API_SPECIFICATION.md §10)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MemoryItemType = Literal["photo", "video", "note"]


class MemoryItemCreateRequest(BaseModel):
    """The mobile client uploads the binary DIRECTLY to Supabase Storage
    (respecting the RLS policies already established in migration
    20260825120013 — the client's own authenticated session, not a
    backend-issued signed URL, since the storage bucket's RLS already
    permits exactly the same author-or-trip-owner access this endpoint
    itself enforces at the metadata layer) and only calls this endpoint to
    record the resulting metadata row, per API_SPECIFICATION.md §10's
    "backend records metadata" contract. `storage_path` must therefore
    already exist in the `memory-items` bucket under this trip/user's
    folder before this call — a NOTE-type item has no storage_path at all."""

    item_type: MemoryItemType
    storage_path: str | None = Field(default=None, max_length=500)
    caption: str | None = Field(default=None, max_length=1000)
    taken_at: datetime | None = None


class MemoryItemResponse(BaseModel):
    id: str
    trip_id: str
    user_id: str
    item_type: MemoryItemType
    storage_path: str | None
    caption: str | None
    taken_at: datetime | None
    uploaded_at: datetime
    retention_expires_at: datetime
    expiry_reminder_sent_at: datetime | None
    downloaded_at: datetime | None
