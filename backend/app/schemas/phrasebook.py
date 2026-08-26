"""Request/response schemas for /v1/phrasebook/* — F10
(API_SPECIFICATION.md §9)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PhrasebookEntryResponse(BaseModel):
    id: str
    region: str
    language_code: str
    category: str
    phrase_en: str
    phrase_local_script: str
    phrase_transliteration: str
    audio_url: str | None
    created_at: datetime
