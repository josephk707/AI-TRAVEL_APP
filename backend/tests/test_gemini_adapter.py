"""
Unit tests for app/services/ai/gemini_adapter.py — message mapping, error
normalization, structured-output parsing, and safety-block handling, all
exercised against a fake `google.genai` client (the SDK's own async model
methods are monkeypatched), never a real network call. No API key, no
cost, no external dependency — mirrors the same boundary-mocking pattern
already established in tests/test_google_places_client.py.

Real, live Gemini API validation (an actual network call with a real
GEMINI_API_KEY) lives in tests/test_llm_gateway_live.py, run only via
scripts/run_live_tests.py.
"""

from __future__ import annotations

from typing import Any

import pytest
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel

from app.services.ai.gemini_adapter import GeminiAdapter
from app.services.ai.llm_gateway import (
    GenerationConfig,
    LLMImage,
    LLMMessage,
    LLMProviderError,
    MessageRole,
)


class _Itinerary(BaseModel):
    summary: str
    day_count: int


def _make_adapter() -> GeminiAdapter:
    return GeminiAdapter(
        "fake-test-key-not-real",
        text_model="gemini-2.5-flash",
        reasoning_model="gemini-2.5-pro",
        embedding_model="gemini-embedding-001",
        embedding_dimensions=1536,
    )


def _make_response(
    text: str,
    *,
    finish_reason: genai_types.FinishReason = genai_types.FinishReason.STOP,
    prompt_tokens: int = 12,
    output_tokens: int = 8,
    block_reason: genai_types.BlockedReason | None = None,
    no_candidates: bool = False,
) -> genai_types.GenerateContentResponse:
    candidates = (
        []
        if no_candidates
        else [
            genai_types.Candidate(
                content=genai_types.Content(
                    role="model", parts=[genai_types.Part.from_text(text=text)]
                ),
                finish_reason=finish_reason,
            )
        ]
    )
    return genai_types.GenerateContentResponse(
        candidates=candidates,
        usage_metadata=genai_types.GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt_tokens, candidates_token_count=output_tokens
        ),
        prompt_feedback=(
            genai_types.GenerateContentResponsePromptFeedback(block_reason=block_reason)
            if block_reason
            else None
        ),
    )


class _FakeAsyncModels:
    def __init__(self, response: Any = None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.captured_kwargs: dict[str, Any] = {}

    async def generate_content(self, **kwargs: Any) -> Any:
        self.captured_kwargs = kwargs
        if self.exc is not None:
            raise self.exc
        return self.response

    async def embed_content(self, **kwargs: Any) -> Any:
        self.captured_kwargs = kwargs
        if self.exc is not None:
            raise self.exc
        return self.response


def _wire(adapter: GeminiAdapter, fake_models: _FakeAsyncModels) -> None:
    # `AsyncClient.models` is a read-only property (no setter) — shadow the
    # two instance methods this adapter actually calls instead of replacing
    # the whole `models` object.
    adapter._client.aio.models.generate_content = fake_models.generate_content  # type: ignore[method-assign]
    adapter._client.aio.models.embed_content = fake_models.embed_content  # type: ignore[method-assign]


async def test_complete_maps_system_and_turns_and_returns_text() -> None:
    adapter = _make_adapter()
    fake = _FakeAsyncModels(response=_make_response("Hello traveller!"))
    _wire(adapter, fake)

    result = await adapter.complete(
        [
            LLMMessage(MessageRole.SYSTEM, "You are a travel companion."),
            LLMMessage(MessageRole.USER, "Plan my trip."),
        ]
    )

    assert result.text == "Hello traveller!"
    assert result.input_tokens == 12
    assert result.output_tokens == 8
    assert result.finish_reason == "STOP"
    assert result.low_confidence_signal is False
    assert fake.captured_kwargs["config"].system_instruction == "You are a travel companion."
    assert len(fake.captured_kwargs["contents"]) == 1
    assert fake.captured_kwargs["contents"][0].role == "user"


async def test_complete_with_response_schema_returns_parsed_model() -> None:
    adapter = _make_adapter()
    fake = _FakeAsyncModels(response=_make_response('{"summary": "Agra trip", "day_count": 3}'))
    _wire(adapter, fake)

    result = await adapter.complete(
        [LLMMessage(MessageRole.USER, "Generate")], response_schema=_Itinerary
    )

    assert isinstance(result.parsed, _Itinerary)
    assert result.parsed.day_count == 3
    assert fake.captured_kwargs["config"].response_mime_type == "application/json"


async def test_complete_raises_on_malformed_structured_json() -> None:
    adapter = _make_adapter()
    fake = _FakeAsyncModels(response=_make_response("not json at all"))
    _wire(adapter, fake)

    with pytest.raises(LLMProviderError) as exc_info:
        await adapter.complete(
            [LLMMessage(MessageRole.USER, "Generate")], response_schema=_Itinerary
        )

    assert exc_info.value.retryable is True
    assert exc_info.value.code == "LLM_MALFORMED_RESPONSE"


async def test_complete_raises_on_schema_validation_failure() -> None:
    adapter = _make_adapter()
    fake = _FakeAsyncModels(response=_make_response('{"summary": "ok"}'))  # missing day_count
    _wire(adapter, fake)

    with pytest.raises(LLMProviderError) as exc_info:
        await adapter.complete(
            [LLMMessage(MessageRole.USER, "Generate")], response_schema=_Itinerary
        )

    assert exc_info.value.code == "LLM_INVALID_STRUCTURED_OUTPUT"


async def test_complete_raises_timeout_error() -> None:
    adapter = _make_adapter()

    async def _hang(**kwargs: Any) -> Any:
        import asyncio

        await asyncio.sleep(10)

    fake = _FakeAsyncModels()
    fake.generate_content = _hang  # type: ignore[method-assign]
    _wire(adapter, fake)

    with pytest.raises(LLMProviderError) as exc_info:
        await adapter.complete(
            [LLMMessage(MessageRole.USER, "hi")], config=GenerationConfig(timeout_seconds=0.01)
        )

    assert exc_info.value.code == "LLM_TIMEOUT"
    assert exc_info.value.retryable is True


async def test_complete_raises_rate_limited_on_429() -> None:
    adapter = _make_adapter()
    fake = _FakeAsyncModels(exc=genai_errors.ClientError(429, {"error": {"message": "quota"}}))
    _wire(adapter, fake)

    with pytest.raises(LLMProviderError) as exc_info:
        await adapter.complete([LLMMessage(MessageRole.USER, "hi")])

    assert exc_info.value.code == "LLM_RATE_LIMITED"
    assert exc_info.value.retryable is True


async def test_complete_raises_server_error_as_retryable() -> None:
    adapter = _make_adapter()
    fake = _FakeAsyncModels(exc=genai_errors.ServerError(503, {"error": {"message": "down"}}))
    _wire(adapter, fake)

    with pytest.raises(LLMProviderError) as exc_info:
        await adapter.complete([LLMMessage(MessageRole.USER, "hi")])

    assert exc_info.value.code == "LLM_SERVER_ERROR"
    assert exc_info.value.retryable is True


async def test_complete_raises_client_error_as_not_retryable() -> None:
    adapter = _make_adapter()
    fake = _FakeAsyncModels(exc=genai_errors.ClientError(400, {"error": {"message": "bad"}}))
    _wire(adapter, fake)

    with pytest.raises(LLMProviderError) as exc_info:
        await adapter.complete([LLMMessage(MessageRole.USER, "hi")])

    assert exc_info.value.code == "LLM_CLIENT_ERROR"
    assert exc_info.value.retryable is False


async def test_complete_raises_on_safety_block() -> None:
    adapter = _make_adapter()
    fake = _FakeAsyncModels(
        response=_make_response(
            "", block_reason=genai_types.BlockedReason.SAFETY, no_candidates=True
        )
    )
    _wire(adapter, fake)

    with pytest.raises(LLMProviderError) as exc_info:
        await adapter.complete([LLMMessage(MessageRole.USER, "hi")])

    assert exc_info.value.code == "LLM_CONTENT_BLOCKED"


async def test_complete_multimodal_attaches_image_to_final_turn_only() -> None:
    adapter = _make_adapter()
    fake = _FakeAsyncModels(response=_make_response("I see the Taj Mahal."))
    _wire(adapter, fake)

    result = await adapter.complete_multimodal(
        [LLMMessage(MessageRole.USER, "What is this?")],
        [LLMImage(data=b"\xff\xd8\xff", mime_type="image/jpeg")],
    )

    assert result.text == "I see the Taj Mahal."
    sent_contents = fake.captured_kwargs["contents"]
    assert len(sent_contents[-1].parts) == 2


async def test_embed_returns_vectors_matching_input_count() -> None:
    adapter = _make_adapter()
    fake_embeddings = genai_types.EmbedContentResponse(
        embeddings=[
            genai_types.ContentEmbedding(values=[0.1, 0.2, 0.3]),
            genai_types.ContentEmbedding(values=[0.4, 0.5, 0.6]),
        ]
    )
    fake = _FakeAsyncModels(response=fake_embeddings)
    _wire(adapter, fake)

    result = await adapter.embed(["a", "b"], dimensions=3)

    assert len(result.vectors) == 2
    assert result.dimensions == 3


async def test_embed_raises_on_count_mismatch() -> None:
    adapter = _make_adapter()
    fake_embeddings = genai_types.EmbedContentResponse(
        embeddings=[genai_types.ContentEmbedding(values=[0.1, 0.2, 0.3])]
    )
    fake = _FakeAsyncModels(response=fake_embeddings)
    _wire(adapter, fake)

    with pytest.raises(LLMProviderError):
        await adapter.embed(["a", "b"], dimensions=3)
