"""Request/response schema for /v1/trips/{id}/offline-package — F26
Offline Heritage Access (IMPLEMENTATION_BLUEPRINT.md F26, resolving the
same "documented only in the Blueprint" gap as F20's disruptions
endpoints — see app/schemas/disruption.py)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.phrasebook import PhrasebookEntryResponse


class OfflinePoi(BaseModel):
    poi_id: str
    name: str
    category: str
    lat: float
    lng: float


class OfflineHeritageSection(BaseModel):
    poi_id: str
    section_title: str | None
    body_text: str
    source_citation: str | None


class OfflinePackageResponse(BaseModel):
    trip_id: str
    packaged_at: datetime
    pois: list[OfflinePoi]
    heritage_content: list[OfflineHeritageSection]
    phrasebook_entries: list[PhrasebookEntryResponse]
