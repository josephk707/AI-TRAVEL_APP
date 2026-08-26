"""
F10 (dynamic extension) — arbitrary-phrase text translation via Gemini.

ARCHITECTURE_REVIEW.md M11: the original F10 scope was curated-phrasebook
only (static content, `phrasebook_entries`); F25 (Phase 2/3) adds live
SPEECH translation. Neither covers a traveller typing an arbitrary phrase
not in the curated set. This module is the documented resolution: a real
Gemini-backed translation call, no lookup table, no hardcoded phrase list —
the traveller can type anything and get a real, grounded-in-context
translation, not a canned response (CLAUDE.md §3/§14 "never hardcode
translations").
"""

from __future__ import annotations

from pydantic import BaseModel

from app.core.exceptions import UpstreamUnavailableError
from app.services.ai.factory import get_llm_gateway
from app.services.ai.llm_gateway import GenerationConfig, LLMMessage, LLMProviderError, MessageRole
from app.services.ai.prompts import translation as translation_prompts


class _TranslationResult(BaseModel):
    translated_text: str
    transliteration: str
    note: str | None = None
    recognized_language: bool = True


async def translate_text(text: str, target_language: str) -> dict:
    gateway = get_llm_gateway()
    if gateway is None:
        raise UpstreamUnavailableError(
            "Translation is temporarily unavailable — the AI provider is not configured.",
            details={"code": "TRANSLATION_NOT_CONFIGURED"},
        )

    try:
        response = await gateway.complete(
            [
                LLMMessage(MessageRole.SYSTEM, translation_prompts.SYSTEM_PROMPT),
                LLMMessage(
                    MessageRole.USER, translation_prompts.build_user_message(text, target_language)
                ),
            ],
            response_schema=_TranslationResult,
            config=GenerationConfig(temperature=0.3, max_output_tokens=512, timeout_seconds=15.0),
        )
    except LLMProviderError as exc:
        raise UpstreamUnavailableError(
            "Translation failed — please try again in a moment.",
            details={"code": "TRANSLATION_PROVIDER_ERROR"},
        ) from exc

    assert isinstance(response.parsed, _TranslationResult)
    result = response.parsed
    return {
        "original_text": text,
        "target_language": target_language,
        "translated_text": result.translated_text,
        "transliteration": result.transliteration,
        "note": result.note,
        "recognized_language": result.recognized_language,
    }
