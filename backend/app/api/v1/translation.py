"""/v1/translate/* — F10 dynamic text translation (ARCHITECTURE_REVIEW.md M11)
+ F25 speech translation (API_SPECIFICATION.md §9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, UploadFile

from app.api.deps import get_current_user
from app.core.rate_limit import ai_rate_limit
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope
from app.schemas.translation import (
    SpeechTranslateResponse,
    TranslateTextRequest,
    TranslateTextResponse,
)
from app.services import speech_translation_service, translation_service

router = APIRouter(prefix="/translate", tags=["translation"])


@router.post("/text", response_model=Envelope[TranslateTextResponse])
async def translate_text(
    body: TranslateTextRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    _rl: None = Depends(ai_rate_limit),
) -> Envelope[TranslateTextResponse]:
    del user
    result = await translation_service.translate_text(body.text, body.target_language)
    return Envelope(data=TranslateTextResponse.model_validate(result))


@router.post("/speech", response_model=Envelope[SpeechTranslateResponse])
async def translate_speech(
    audio: UploadFile,
    target_language: str = Form(..., min_length=2, max_length=40),
    user: AuthenticatedUser = Depends(get_current_user),
    _rl: None = Depends(ai_rate_limit),
) -> Envelope[SpeechTranslateResponse]:
    """Batch audio-clip translation — see speech_translation_service.py's
    module docstring for the real-time-vs-batch honesty boundary."""
    del user
    audio_bytes = await audio.read()
    result = await speech_translation_service.translate_speech(
        audio_bytes, audio.content_type or "application/octet-stream", target_language
    )
    return Envelope(data=SpeechTranslateResponse.model_validate(result))
