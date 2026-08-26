"""
Google Gemini adapter — the ONLY place in this codebase that imports the
`google.genai` SDK, per CLAUDE.md §8 ("every call site goes through the
gateway interface, so the provider is a config choice, not a hardcoded
dependency") and AI_ARCHITECTURE.md §1. Every business-logic service
(itinerary generation, idea extraction, conversational modification,
heritage narration, visual Q&A, translation) depends on `LLMGateway`
(llm_gateway.py), never on this class or the `google.genai` types directly.

Content safety: every call sets explicit `safety_settings` — never left at
provider defaults, and never set to `BLOCK_NONE`/`OFF` (AI_ARCHITECTURE.md
§10 "provider-level content-safety settings enabled on every LLMGateway
adapter"). A safety-blocked response is surfaced as a typed
`LLMProviderError`, never silently returned as an empty success.

Error normalization: every `google.genai.errors.APIError` (and timeout) is
caught here and re-raised as `LLMProviderError` — no raw Gemini SDK
exception, HTTP status, or error body ever reaches a caller, per
CLAUDE.md §9's "external API failures degrade gracefully" and §19
(AI security) "no unnecessary sensitive context in logs" — the API key is
passed to the SDK once, at client-construction time, and never appears in
any exception message this module raises.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel

from app.services.ai.llm_gateway import (
    EmbeddingResponse,
    GenerationConfig,
    LLMImage,
    LLMMessage,
    LLMProviderError,
    LLMResponse,
    MessageRole,
    parse_structured_response,
)

logger = logging.getLogger("app.ai.gemini")

# Never BLOCK_NONE/OFF — a deliberate, permanent choice (AI_ARCHITECTURE.md
# §10), not a default left unexamined.
_SAFETY_SETTINGS = [
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=genai_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
]

_ROLE_MAP = {MessageRole.USER: "user", MessageRole.ASSISTANT: "model"}


def _split_system_and_turns(messages: Sequence[LLMMessage]) -> tuple[str | None, list[LLMMessage]]:
    system_parts = [m.content for m in messages if m.role is MessageRole.SYSTEM]
    turns = [m for m in messages if m.role is not MessageRole.SYSTEM]
    return ("\n\n".join(system_parts) if system_parts else None), turns


def _build_contents(
    turns: list[LLMMessage], extra_parts: list[genai_types.Part] | None = None
) -> list[genai_types.Content]:
    """Maps our provider-agnostic message list onto Gemini's `Content` list.
    `extra_parts` (images/audio) are attached to the FINAL turn only — the
    current request, never spliced into prior conversation history."""
    contents: list[genai_types.Content] = []
    for index, turn in enumerate(turns):
        parts = [genai_types.Part.from_text(text=turn.content)]
        if extra_parts and index == len(turns) - 1:
            parts = parts + extra_parts
        contents.append(genai_types.Content(role=_ROLE_MAP[turn.role], parts=parts))
    return contents


def _finish_reason_value(response: genai_types.GenerateContentResponse) -> str | None:
    if response.candidates:
        reason = response.candidates[0].finish_reason
        return reason.value if reason is not None else None
    return None


def _is_safety_blocked(response: genai_types.GenerateContentResponse) -> bool:
    if response.prompt_feedback is not None and response.prompt_feedback.block_reason is not None:
        return True
    finish = _finish_reason_value(response)
    return finish in {"SAFETY", "PROHIBITED_CONTENT", "IMAGE_SAFETY", "IMAGE_PROHIBITED_CONTENT"}


class GeminiAdapter:
    """Implements `LLMGateway` (structurally — Python Protocols are
    duck-typed, no explicit inheritance required) against Google Gemini."""

    def __init__(
        self,
        api_key: str,
        *,
        text_model: str,
        reasoning_model: str,
        embedding_model: str,
        embedding_dimensions: int,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self.text_model = text_model
        self.reasoning_model = reasoning_model
        self.embedding_model = embedding_model
        self.embedding_dimensions = embedding_dimensions

    def _build_config(
        self,
        system_instruction: str | None,
        config: GenerationConfig,
        response_schema: type[BaseModel] | None,
    ) -> genai_types.GenerateContentConfig:
        return genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=config.temperature,
            max_output_tokens=config.max_output_tokens,
            safety_settings=_SAFETY_SETTINGS,
            response_mime_type="application/json" if response_schema else None,
            response_schema=response_schema,
        )

    async def _generate(
        self,
        model: str,
        contents: list[genai_types.Content],
        gen_config: genai_types.GenerateContentConfig,
        timeout_seconds: float,
    ) -> genai_types.GenerateContentResponse:
        try:
            return await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=model, contents=contents, config=gen_config
                ),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            raise LLMProviderError(
                "Gemini request timed out.", retryable=True, code="LLM_TIMEOUT"
            ) from exc
        except genai_errors.ClientError as exc:
            retryable = exc.code == 429
            code = "LLM_RATE_LIMITED" if exc.code == 429 else "LLM_CLIENT_ERROR"
            logger.warning("gemini_client_error", extra={"status": exc.code})
            raise LLMProviderError(
                "Gemini rejected the request." if not retryable else "Gemini rate limit exceeded.",
                retryable=retryable,
                code=code,
            ) from exc
        except genai_errors.ServerError as exc:
            logger.warning("gemini_server_error", extra={"status": exc.code})
            raise LLMProviderError(
                "Gemini is temporarily unavailable.", retryable=True, code="LLM_SERVER_ERROR"
            ) from exc
        except genai_errors.APIError as exc:
            logger.warning("gemini_api_error", extra={"status": exc.code})
            raise LLMProviderError(
                "Gemini returned an unexpected error.", retryable=False, code="LLM_PROVIDER_ERROR"
            ) from exc

    def _to_llm_response(
        self,
        response: genai_types.GenerateContentResponse,
        model: str,
        response_schema: type[BaseModel] | None,
    ) -> LLMResponse:
        if not response.candidates or _is_safety_blocked(response):
            logger.info("gemini_response_blocked_or_empty")
            raise LLMProviderError(
                "Gemini declined to answer (content-safety or empty response).",
                retryable=False,
                code="LLM_CONTENT_BLOCKED",
            )

        text = response.text or ""
        parsed: BaseModel | None = None
        if response_schema is not None:
            parsed = parse_structured_response(text, response_schema)

        usage = response.usage_metadata
        finish_reason = _finish_reason_value(response)
        return LLMResponse(
            text=text,
            parsed=parsed,
            model=model,
            input_tokens=usage.prompt_token_count if usage else None,
            output_tokens=usage.candidates_token_count if usage else None,
            finish_reason=finish_reason,
            low_confidence_signal=finish_reason not in {None, "STOP"},
        )

    async def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        response_schema: type[BaseModel] | None = None,
        config: GenerationConfig = GenerationConfig(),
    ) -> LLMResponse:
        system_instruction, turns = _split_system_and_turns(messages)
        contents = _build_contents(turns)
        model = self.reasoning_model if response_schema is None else self.text_model
        gen_config = self._build_config(system_instruction, config, response_schema)
        response = await self._generate(model, contents, gen_config, config.timeout_seconds)
        return self._to_llm_response(response, model, response_schema)

    async def complete_multimodal(
        self,
        messages: Sequence[LLMMessage],
        images: Sequence[LLMImage],
        *,
        response_schema: type[BaseModel] | None = None,
        config: GenerationConfig = GenerationConfig(),
    ) -> LLMResponse:
        system_instruction, turns = _split_system_and_turns(messages)
        image_parts = [
            genai_types.Part.from_bytes(data=img.data, mime_type=img.mime_type) for img in images
        ]
        contents = _build_contents(turns, extra_parts=image_parts)
        gen_config = self._build_config(system_instruction, config, response_schema)
        response = await self._generate(
            self.text_model, contents, gen_config, config.timeout_seconds
        )
        return self._to_llm_response(response, self.text_model, response_schema)

    async def complete_audio(
        self,
        messages: Sequence[LLMMessage],
        audio: bytes,
        audio_mime_type: str,
        *,
        response_schema: type[BaseModel] | None = None,
        config: GenerationConfig = GenerationConfig(),
    ) -> LLMResponse:
        system_instruction, turns = _split_system_and_turns(messages)
        audio_part = genai_types.Part.from_bytes(data=audio, mime_type=audio_mime_type)
        contents = _build_contents(turns, extra_parts=[audio_part])
        gen_config = self._build_config(system_instruction, config, response_schema)
        response = await self._generate(
            self.text_model, contents, gen_config, config.timeout_seconds
        )
        return self._to_llm_response(response, self.text_model, response_schema)

    async def embed(
        self,
        texts: Sequence[str],
        *,
        dimensions: int,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> EmbeddingResponse:
        try:
            response = await asyncio.wait_for(
                self._client.aio.models.embed_content(
                    model=self.embedding_model,
                    contents=list(texts),
                    config=genai_types.EmbedContentConfig(
                        output_dimensionality=dimensions, task_type=task_type
                    ),
                ),
                timeout=30.0,
            )
        except TimeoutError as exc:
            raise LLMProviderError(
                "Gemini embedding request timed out.", retryable=True, code="LLM_TIMEOUT"
            ) from exc
        except genai_errors.APIError as exc:
            logger.warning("gemini_embed_error", extra={"status": exc.code})
            raise LLMProviderError(
                "Gemini embedding request failed.",
                retryable=exc.code in (429, 500, 502, 503),
                code="LLM_EMBEDDING_ERROR",
            ) from exc

        if not response.embeddings:
            raise LLMProviderError(
                "Gemini returned no embeddings.", retryable=True, code="LLM_MALFORMED_RESPONSE"
            )
        vectors = [list(e.values) for e in response.embeddings if e.values is not None]
        if len(vectors) != len(texts):
            raise LLMProviderError(
                "Gemini returned a different number of embeddings than requested.",
                retryable=True,
                code="LLM_MALFORMED_RESPONSE",
            )
        return EmbeddingResponse(vectors=vectors, model=self.embedding_model, dimensions=dimensions)
