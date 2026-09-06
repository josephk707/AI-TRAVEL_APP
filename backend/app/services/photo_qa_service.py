"""
F9 — Photo-Based Landmark Q&A / Visual Q&A (IMPLEMENTATION_BLUEPRINT.md F9,
AI_ARCHITECTURE.md §6, API_SPECIFICATION.md §8).

Grounds the multimodal answer against the SAME retrieved heritage content
chunks the narration feature (F8) uses for this poi_id, per §6 step 2 —
"not a separate unguided vision call." Confidence is a combination of
whether grounding content existed AND the model's own report of whether
the photo matches it (this endpoint, unlike narration, explicitly permits
that self-report per §6 step 3 — a different guardrail than F8's stricter
"never ask the model if it's confident").
"""

from __future__ import annotations

from pydantic import BaseModel

from app.core.exceptions import AppError, UpstreamUnavailableError
from app.repositories.ai_conversations_repository import AiConversationsRepository
from app.repositories.heritage_repository import HeritageRepository
from app.repositories.pois_repository import PoisRepository
from app.repositories.profiles_repository import ProfilesRepository
from app.services.ai.factory import get_llm_gateway
from app.services.ai.language import language_instruction
from app.services.ai.llm_gateway import (
    GenerationConfig,
    LLMImage,
    LLMMessage,
    LLMProviderError,
    MessageRole,
)
from app.services.ai.prompts import photo_qa as photo_qa_prompts

_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_IMAGE_BYTES = 8 * 1024 * 1024


class _PhotoQaResult(BaseModel):
    answer: str
    matches_source: bool = False


def validate_image(image_bytes: bytes, mime_type: str) -> None:
    if mime_type not in _ALLOWED_MIME_TYPES:
        raise AppError(
            "IMAGE_UNUSABLE",
            "That image format isn't supported — please retake the photo (JPEG, PNG, or WebP).",
            422,
        )
    if not image_bytes:
        raise AppError("IMAGE_UNUSABLE", "That image looks empty — please retake it.", 422)
    if len(image_bytes) > _MAX_IMAGE_BYTES:
        raise AppError(
            "IMAGE_UNUSABLE", "That image is too large — please retake at a lower resolution.", 422
        )


async def answer_photo_question(
    poi_id: str | None,
    question: str,
    image_bytes: bytes,
    image_mime_type: str,
    user_id: str | None = None,
) -> dict:
    validate_image(image_bytes, image_mime_type)

    gateway = get_llm_gateway()
    if gateway is None:
        raise UpstreamUnavailableError(
            "Visual Q&A is temporarily unavailable — the AI provider is not configured.",
            details={"code": "PHOTO_QA_NOT_CONFIGURED"},
        )

    poi_name = None
    chunks: list[dict] = []
    if poi_id:
        poi = await PoisRepository().get_by_id(poi_id)
        if poi is not None:
            poi_name = poi["name"]
            chunks = await HeritageRepository().get_published_content(poi_id, "overview")

    preferred_language: str | None = None
    if user_id:
        profile = await ProfilesRepository().get_by_id(user_id)
        raw_language = (profile or {}).get("preferred_language")
        preferred_language = str(raw_language) if raw_language else None
    system_prompt = photo_qa_prompts.SYSTEM_PROMPT + language_instruction(preferred_language)

    try:
        response = await gateway.complete_multimodal(
            [
                LLMMessage(MessageRole.SYSTEM, system_prompt),
                LLMMessage(
                    MessageRole.USER,
                    photo_qa_prompts.build_user_message(question, poi_name, chunks),
                ),
            ],
            [LLMImage(data=image_bytes, mime_type=image_mime_type)],
            response_schema=_PhotoQaResult,
            config=GenerationConfig(temperature=0.4, max_output_tokens=768, timeout_seconds=20.0),
        )
    except LLMProviderError as exc:
        raise UpstreamUnavailableError(
            "Visual Q&A failed — please try again in a moment.",
            details={"code": "PHOTO_QA_PROVIDER_ERROR"},
        ) from exc

    assert isinstance(response.parsed, _PhotoQaResult)
    result = response.parsed
    grounded = bool(chunks) and result.matches_source
    confidence = "high" if grounded else "low"

    # Logged for audit/golden-set purposes (M8 fix — context_type='photo_qa',
    # conversation_id NULL), never client-readable directly (DATABASE_SCHEMA.md §10).
    await AiConversationsRepository().log_photo_qa(
        content=result.answer, role="assistant", model=response.model, confidence=confidence
    )

    return {
        "poi_id": poi_id,
        "answer": result.answer,
        "confidence": confidence,
        "grounded": grounded,
    }
