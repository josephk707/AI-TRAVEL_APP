"""Unit tests for app/services/translation_service.py — the LLM gateway is
monkeypatched at its factory boundary (app.services.ai.factory.get_llm_gateway),
never a real network call."""

from __future__ import annotations

import pytest

from app.core.exceptions import UpstreamUnavailableError
from app.services import translation_service
from app.services.ai.llm_gateway import LLMProviderError, LLMResponse
from app.services.translation_service import _TranslationResult


class _FakeGateway:
    def __init__(self, result: _TranslationResult | None = None, error: Exception | None = None):
        self._result = result
        self._error = error

    async def complete(self, messages, *, response_schema=None, config=None):
        if self._error:
            raise self._error
        return LLMResponse(text="{}", parsed=self._result, model="fake-model")


async def test_translate_text_returns_the_llm_result(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeGateway(
        result=_TranslationResult(
            translated_text="निकटतम रेलवे स्टेशन कहाँ है?",
            transliteration="Nikatatam railway station kahaan hai?",
            recognized_language=True,
        )
    )
    monkeypatch.setattr(translation_service, "get_llm_gateway", lambda: fake)

    result = await translation_service.translate_text(
        "Where is the nearest railway station?", "Hindi"
    )

    assert result["translated_text"] == "निकटतम रेलवे स्टेशन कहाँ है?"
    assert result["transliteration"] == "Nikatatam railway station kahaan hai?"
    assert result["target_language"] == "Hindi"
    assert result["original_text"] == "Where is the nearest railway station?"
    assert result["recognized_language"] is True


async def test_translate_text_raises_upstream_unavailable_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(translation_service, "get_llm_gateway", lambda: None)

    with pytest.raises(UpstreamUnavailableError):
        await translation_service.translate_text("hello", "Hindi")


async def test_translate_text_raises_upstream_unavailable_on_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeGateway(error=LLMProviderError("boom", retryable=True))
    monkeypatch.setattr(translation_service, "get_llm_gateway", lambda: fake)

    with pytest.raises(UpstreamUnavailableError):
        await translation_service.translate_text("hello", "Hindi")
