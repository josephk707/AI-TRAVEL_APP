"""
LLM Gateway factory — the single place `Settings.gemini_api_key` is read
and turned into a concrete adapter. Every service imports `get_llm_gateway`
from here, never `GeminiAdapter` directly (CLAUDE.md §8).

Returns `None` when no provider key is configured, exactly like
`google_maps_api_key`'s pattern in `poi_service.py` — every caller is
required to treat "AI not configured" as a graceful-degradation path
(fallback template, `meta.degraded_mode`), never a crash.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.services.ai.gemini_adapter import GeminiAdapter
from app.services.ai.llm_gateway import LLMGateway


@lru_cache
def get_llm_gateway() -> LLMGateway | None:
    settings = get_settings()
    if settings.gemini_api_key is None:
        return None
    return GeminiAdapter(
        settings.gemini_api_key.get_secret_value(),
        text_model=settings.gemini_text_model,
        reasoning_model=settings.gemini_reasoning_model,
        embedding_model=settings.gemini_embedding_model,
        embedding_dimensions=settings.gemini_embedding_dimensions,
    )
