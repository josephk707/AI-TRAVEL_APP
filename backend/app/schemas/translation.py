"""Request/response schemas for /v1/translate/text — F10 dynamic
(arbitrary-phrase) translation. See app/services/translation_service.py's
module docstring for the ARCHITECTURE_REVIEW.md M11 resolution this
implements."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

# Final Personalization phase (Part 8/9) — the prototype is explicitly
# scoped to at most two sentences. A simple, real sentence-boundary count
# (., !, ? followed by whitespace/end-of-string), not a fabricated limit —
# matches what the mobile screen itself counts and shows the user live.
_MAX_SENTENCES = 2
_SENTENCE_BOUNDARY = re.compile(r"[.!?]+(?:\s|$)")


def _count_sentences(text: str) -> int:
    # Splits on sentence-ending punctuation; a trailing fragment with no
    # terminal punctuation still counts as one (real) sentence, matching
    # how a person would naturally read "Where is the station" (no "?")
    # as one phrase, not zero.
    fragments = [f for f in _SENTENCE_BOUNDARY.split(text) if f.strip()]
    return max(len(fragments), 1 if text.strip() else 0)


class TranslateTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    target_language: str = Field(
        min_length=2, max_length=40, description="e.g. 'Hindi', 'Telugu', 'Malayalam', 'Kannada'"
    )

    @field_validator("text")
    @classmethod
    def _limit_to_two_sentences(cls, value: str) -> str:
        count = _count_sentences(value)
        if count > _MAX_SENTENCES:
            raise ValueError(
                f"This prototype translates at most {_MAX_SENTENCES} sentences at a time "
                f"(found {count})."
            )
        return value


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
