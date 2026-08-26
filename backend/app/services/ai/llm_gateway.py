"""
LLM Gateway — provider abstraction (AI_ARCHITECTURE.md §1).

The PRD deliberately never names an LLM vendor. Every AI-facing service in
this codebase (itinerary generation, idea extraction, conversational
modification, heritage narration RAG, visual Q&A, translation) is written
against the `LLMGateway` protocol below, NEVER against a vendor SDK
directly — this is what makes the concrete provider (currently Gemini,
`app/services/ai/gemini_adapter.py`) a config value (`Settings.llm_provider`)
rather than an architectural commitment. A future second provider is a new
adapter class implementing this same protocol, not a rewrite of any call
site (CLAUDE.md §8).

Structured output: `complete()`/`complete_multimodal()` accept an optional
`response_schema` (a pydantic `BaseModel` subclass). When provided, the
adapter is responsible for requesting a schema-constrained response from
the provider AND for returning `LLMResponse.parsed` as a validated instance
of that model — never a hand-rolled string-scraping parse of freeform text
(CLAUDE.md §8 "validate model responses before persisting or returning").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class LLMMessage:
    role: MessageRole
    content: str


@dataclass(frozen=True)
class LLMImage:
    """An inline image for a multimodal call — raw bytes, never a URL the
    provider would have to fetch itself (keeps the trust boundary at this
    backend, per CLAUDE.md §8's "AI calls receive only necessary context")."""

    data: bytes
    mime_type: str


@dataclass(frozen=True)
class LLMResponse:
    text: str
    parsed: BaseModel | None = None
    model: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    low_confidence_signal: bool = False
    """Provider- or content-safety-reported low-confidence/uncertainty
    marker, if the underlying model surfaces one (e.g. a safety-block, a
    refusal, or a self-reported uncertainty). This is NEVER the sole
    source of a product-facing confidence flag (AI_ARCHITECTURE.md §5.2.4
    requires that to be a structural property of retrieval quality) — it
    is one additional signal callers may combine with their own."""


@dataclass(frozen=True)
class EmbeddingResponse:
    vectors: list[list[float]]
    model: str = ""
    dimensions: int = 0


class LLMProviderError(Exception):
    """Raised for ANY provider failure — timeout, rate limit, malformed
    response, content-safety rejection, auth failure, quota exceeded. A
    caller only ever needs to catch this one type, never a vendor SDK
    exception (CLAUDE.md §9's "external API failures degrade gracefully").
    `retryable` distinguishes a transient failure (timeout, 5xx, rate
    limit) a caller may retry-with-backoff from a permanent one (invalid
    key, safety rejection) it should not."""

    def __init__(self, message: str, *, retryable: bool = False, code: str = "LLM_PROVIDER_ERROR"):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


@dataclass(frozen=True)
class GenerationConfig:
    max_output_tokens: int = 2048
    temperature: float = 0.7
    timeout_seconds: float = 30.0
    thinking_budget: int = 0
    """Real, live-testing-discovered configuration issue (Phase 6
    certification pass): the Gemini 3.x model family thinks by default,
    and internal 'thought' tokens are drawn from the SAME
    `max_output_tokens` budget as the visible answer — a low budget (fine
    for a short structured JSON reply under the 2.x family) could return
    an empty response (`finish_reason=MAX_TOKENS`, no text) once thinking
    consumed the whole budget. Every pipeline in this codebase needs a
    fast, deterministic, budget-fitting reply (itinerary JSON, a
    translation, a narration paragraph) rather than an extended reasoning
    trace, and the 8-12s/3-5s PRD latency targets (§15) don't leave room
    for open-ended thinking either — so thinking is disabled by default
    (0 = off, the value Gemini's `ThinkingConfig.thinking_budget`
    documents for fully disabling it) across every call site. A future
    pipeline that specifically wants deeper reasoning can override this
    per-call without changing the default."""
    """Provider-level content-safety settings are always enabled (never
    disabled) — see each adapter's own module docstring for how this is
    wired (AI_ARCHITECTURE.md §10)."""


class LLMGateway(Protocol):
    """Every concrete adapter (GeminiAdapter, ...) implements this exactly.
    Business-logic services depend on this Protocol type, never on a
    concrete adapter class, so they type-check against any provider."""

    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        response_schema: type[BaseModel] | None = None,
        config: GenerationConfig = field(default_factory=GenerationConfig),
    ) -> LLMResponse: ...

    async def complete_multimodal(
        self,
        messages: Sequence[LLMMessage],
        images: Sequence[LLMImage],
        *,
        response_schema: type[BaseModel] | None = None,
        config: GenerationConfig = field(default_factory=GenerationConfig),
    ) -> LLMResponse: ...

    async def complete_audio(
        self,
        messages: Sequence[LLMMessage],
        audio: bytes,
        audio_mime_type: str,
        *,
        response_schema: type[BaseModel] | None = None,
        config: GenerationConfig = field(default_factory=GenerationConfig),
    ) -> LLMResponse: ...

    async def embed(
        self,
        texts: Sequence[str],
        *,
        dimensions: int,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> EmbeddingResponse: ...


def parse_structured_response(raw_text: str, schema: type[SchemaT]) -> SchemaT:
    """Shared helper: every adapter funnels its raw JSON text through this
    exact validation step before ever constructing an `LLMResponse.parsed`
    — a single, auditable point where "never trust a model response
    blindly" (CLAUDE.md §8) is enforced, rather than each adapter
    reimplementing its own ad hoc parse."""
    import json

    try:
        payload: Any = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise LLMProviderError(
            "The model returned a response that was not valid JSON.",
            retryable=True,
            code="LLM_MALFORMED_RESPONSE",
        ) from exc

    try:
        return schema.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 - pydantic ValidationError, normalized below
        raise LLMProviderError(
            "The model's structured response failed schema validation.",
            retryable=True,
            code="LLM_INVALID_STRUCTURED_OUTPUT",
        ) from exc
