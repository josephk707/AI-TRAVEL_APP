"""
F25 — Live Speech Translation (API_SPECIFICATION.md §9, IMPLEMENTATION_BLUEPRINT.md F25).

ARCHITECTURE DECISION, documented per CLAUDE.md §13: `API_SPECIFICATION.md`
originally described this endpoint as "proxies a licensed live-translation
provider." This project's LLM provider (Gemini) has native audio-input
understanding (`LLMGateway.complete_audio`), so a separate speech-to-text/
translation vendor is not needed — the same provider abstraction handles
it, one fewer external dependency and cost line. The documented `502 +
meta.degraded_mode` fallback becomes this codebase's standard `503
UPSTREAM_UNAVAILABLE` shape (matching every other AI endpoint's degrade
path), not a functional change to the guarantee itself.

HONESTY BOUNDARY (CLAUDE.md §15 — do not overclaim a real-time capability):
this is BATCH audio understanding — the client records a short clip,
uploads it whole, and receives a transcription+translation once processing
completes. It is not a continuous, full-duplex, real-time voice-to-voice
stream. Gemini's separate Live API (bidirectional WebSocket audio
streaming) would be required for that, and is NOT implemented this phase —
documented here as the concrete provider-capability boundary, not silently
glossed over.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.core.exceptions import AppError, UpstreamUnavailableError
from app.services.ai.factory import get_llm_gateway
from app.services.ai.llm_gateway import GenerationConfig, LLMMessage, LLMProviderError, MessageRole
from app.services.ai.prompts import speech_translation as speech_prompts

_ALLOWED_MIME_TYPES = {
    "audio/mp4",
    "audio/m4a",
    "audio/aac",
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/ogg",
    "audio/flac",
}
_MAX_AUDIO_BYTES = 10 * 1024 * 1024


class _SpeechTranslationResult(BaseModel):
    transcribed_text: str
    translated_text: str
    transliteration: str
    note: str | None = None


def _validate_audio(audio_bytes: bytes, mime_type: str) -> None:
    if mime_type not in _ALLOWED_MIME_TYPES:
        raise AppError("AUDIO_UNUSABLE", f"That audio format ({mime_type}) isn't supported.", 422)
    if not audio_bytes:
        raise AppError("AUDIO_UNUSABLE", "That recording looks empty — please try again.", 422)
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise AppError("AUDIO_UNUSABLE", "That recording is too long — please keep it brief.", 422)


async def translate_speech(audio_bytes: bytes, mime_type: str, target_language: str) -> dict:
    _validate_audio(audio_bytes, mime_type)

    gateway = get_llm_gateway()
    if gateway is None:
        raise UpstreamUnavailableError(
            "Speech translation is temporarily unavailable — the AI provider is not configured.",
            details={"code": "SPEECH_TRANSLATION_NOT_CONFIGURED"},
        )

    try:
        response = await gateway.complete_audio(
            [
                LLMMessage(MessageRole.SYSTEM, speech_prompts.SYSTEM_PROMPT),
                LLMMessage(MessageRole.USER, speech_prompts.build_user_message(target_language)),
            ],
            audio_bytes,
            mime_type,
            response_schema=_SpeechTranslationResult,
            config=GenerationConfig(temperature=0.3, max_output_tokens=512, timeout_seconds=20.0),
        )
    except LLMProviderError as exc:
        raise UpstreamUnavailableError(
            "Speech translation failed — please try again.",
            details={"code": "SPEECH_TRANSLATION_PROVIDER_ERROR"},
        ) from exc

    assert isinstance(response.parsed, _SpeechTranslationResult)
    result = response.parsed
    return {
        "transcribed_text": result.transcribed_text,
        "target_language": target_language,
        "translated_text": result.translated_text,
        "transliteration": result.transliteration,
        "note": result.note,
    }
