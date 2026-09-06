"""
F8 — Heritage Narration RAG Pipeline (IMPLEMENTATION_BLUEPRINT.md F8,
AI_ARCHITECTURE.md §5.2, API_SPECIFICATION.md §7).

Two retrieval modes, exactly as documented:
  - No `section` given ("give me the overview"): a plain poi_id+layer
    filter — no embedding call needed (§5.2 step 1). Works even without a
    configured Gemini key for RETRIEVAL; only the composition step needs it.
  - `section` given (semantic navigation, e.g. "tell me about the
    carvings"): real pgvector cosine-similarity search over
    `heritage_content_embeddings`. BLOCKED without embeddings existing
    (scripts/embed_heritage_content.py, itself blocked without a
    GEMINI_API_KEY) — falls back to the plain filter rather than erroring,
    since some real content is still better than none.

Confidence is ALWAYS a structural property of retrieval, never the model's
own self-report (§5.2 step 4): plain-filter retrieval against real
curated content is "high"; vector search below a similarity threshold, or
finding nothing, is "low".

If NO published content exists for the poi_id at all: 404 POI_NOT_COVERED,
no LLM call made, no fabricated narration (§5.2 step 5 — a hard rule).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.exceptions import AppError, NotFoundError, UpstreamUnavailableError
from app.repositories.heritage_repository import HeritageRepository
from app.repositories.pois_repository import PoisRepository
from app.repositories.profiles_repository import ProfilesRepository
from app.services.ai.factory import get_llm_gateway
from app.services.ai.language import language_instruction
from app.services.ai.llm_gateway import GenerationConfig, LLMMessage, LLMProviderError, MessageRole
from app.services.ai.prompts import narration as narration_prompts

_SIMILARITY_CONFIDENCE_THRESHOLD = 0.55


class _NarrationSchema(BaseModel):
    narration: str


def _poi_not_covered(poi_name: str) -> AppError:
    return AppError(
        "POI_NOT_COVERED",
        f"We don't have verified heritage information for {poi_name} yet.",
        404,
    )


async def get_narration(
    poi_id: str, layer: str, section: str | None, user_id: str | None = None
) -> dict[str, Any]:
    poi = await PoisRepository().get_by_id(poi_id)
    if poi is None:
        raise NotFoundError("This place could not be found.")

    heritage_repo = HeritageRepository()
    if not await heritage_repo.has_any_published_content(poi_id):
        raise _poi_not_covered(poi["name"])

    confidence = "high"
    chunks: list[dict[str, Any]]

    if section:
        gateway = get_llm_gateway()
        vector_hits: list[dict[str, Any]] = []
        if gateway is not None:
            settings = get_settings()
            try:
                embedding = await gateway.embed(
                    [section],
                    dimensions=settings.gemini_embedding_dimensions,
                    task_type="RETRIEVAL_QUERY",
                )
                vector_hits = await heritage_repo.vector_search(poi_id, layer, embedding.vectors[0])
            except LLMProviderError:
                vector_hits = []
        if vector_hits:
            chunks = vector_hits
            best_similarity = vector_hits[0].get("similarity", 0.0)
            confidence = "high" if best_similarity >= _SIMILARITY_CONFIDENCE_THRESHOLD else "low"
        else:
            chunks = await heritage_repo.get_published_content(poi_id, layer)
            confidence = "low"  # section-specific request answered from the general layer only
    else:
        chunks = await heritage_repo.get_published_content(poi_id, layer)

    if not chunks:
        # This layer specifically has nothing, even though some other
        # layer for this POI does — degrade to whatever exists rather than
        # a hard 404 (the POI itself IS covered).
        chunks = await heritage_repo.get_published_content(poi_id)
        confidence = "low"

    if not chunks:
        raise _poi_not_covered(poi["name"])

    gateway = get_llm_gateway()
    if gateway is None:
        raise UpstreamUnavailableError(
            "Heritage narration is temporarily unavailable — the AI provider is not configured.",
            details={"code": "NARRATION_NOT_CONFIGURED"},
        )

    preferred_language: str | None = None
    if user_id:
        profile = await ProfilesRepository().get_by_id(user_id)
        raw_language = (profile or {}).get("preferred_language")
        preferred_language = str(raw_language) if raw_language else None
    system_prompt = narration_prompts.SYSTEM_PROMPT + language_instruction(preferred_language)

    try:
        response = await gateway.complete(
            [
                LLMMessage(MessageRole.SYSTEM, system_prompt),
                LLMMessage(
                    MessageRole.USER,
                    narration_prompts.build_user_message(poi["name"], layer, section, chunks),
                ),
            ],
            response_schema=_NarrationSchema,
            config=GenerationConfig(temperature=0.4, max_output_tokens=1024, timeout_seconds=15.0),
        )
    except LLMProviderError as exc:
        raise UpstreamUnavailableError(
            "Heritage narration failed — please try again in a moment.",
            details={"code": "NARRATION_PROVIDER_ERROR"},
        ) from exc

    assert isinstance(response.parsed, _NarrationSchema)
    return {
        "poi_id": poi_id,
        "poi_name": poi["name"],
        "layer": layer,
        "narration": response.parsed.narration,
        "confidence": confidence,
        "sources": [c["section_title"] for c in chunks],
    }
