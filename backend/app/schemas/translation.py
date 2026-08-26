"""Request/response schemas for /v1/translate/text — F10 dynamic
(arbitrary-phrase) translation. See app/services/translation_service.py's
module docstring for the ARCHITECTURE_REVIEW.md M11 resolution this
implements."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TranslateTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    target_language: str = Field(
        min_length=2, max_length=40, description="e.g. 'Hindi', 'Telugu', 'Malayalam', 'Kannada'"
    )


class TranslateTextResponse(BaseModel):
    original_text: str
    target_language: str
    translated_text: str
    transliteration: str
    note: str | None = None
    recognized_language: bool


class SpeechTranslateResponse(BaseModel):
    transcribed_text: str
    target_language: str
    translated_text: str
    transliteration: str
    note: str | None = None
