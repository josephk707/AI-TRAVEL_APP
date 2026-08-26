"""
Integration tests for POST /v1/translate/speech — F25 (API_SPECIFICATION.md
§9). The Gemini audio boundary is monkeypatched for the success path (same
discipline as test_trips_api.py); the "not configured" path exercises this
environment's real current state (no GEMINI_API_KEY).

Run with:
  python scripts/run_live_tests.py tests/test_speech_translation_api.py -v
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import AsyncClient

from app.services.ai import factory as ai_factory
from app.services.ai.llm_gateway import LLMResponse

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and SUPABASE_URL and SERVICE_ROLE_KEY and ANON_KEY),
    reason="Full Supabase configuration not set — speech translation tests skipped",
)

_TINY_WAV_HEADER = b"RIFF" + b"\x00" * 4 + b"WAVEfmt " + b"\x00" * 40


def _admin_headers() -> dict[str, str]:
    return {"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"}


class _RealSession:
    def __init__(self, user_id: str, access_token: str) -> None:
        self.user_id = user_id
        self.access_token = access_token

    @property
    def auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


async def _create_real_session(http: httpx.AsyncClient, tag: str) -> _RealSession:
    email = f"speech-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
    password = uuid.uuid4().hex
    create_response = await http.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=_admin_headers(),
        json={"email": email, "email_confirm": True, "password": password},
    )
    create_response.raise_for_status()
    user_id = create_response.json()["id"]
    token_response = await http.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON_KEY},
        json={"email": email, "password": password},
    )
    token_response.raise_for_status()
    return _RealSession(user_id, token_response.json()["access_token"])


async def _delete_user(http: httpx.AsyncClient, user_id: str) -> None:
    response = await http.delete(
        f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}", headers=_admin_headers()
    )
    if response.status_code not in (200, 204, 404):
        response.raise_for_status()


@pytest.fixture
async def real_session() -> AsyncIterator[_RealSession]:
    async with httpx.AsyncClient(timeout=15) as http:
        session = await _create_real_session(http, "speech")
        try:
            yield session
        finally:
            await _delete_user(http, session.user_id)


class _FakeGateway:
    def __init__(self, parsed) -> None:
        self._parsed = parsed

    async def complete_audio(
        self, messages, audio, audio_mime_type, *, response_schema=None, config=None
    ):
        return LLMResponse(text="{}", parsed=self._parsed, model="fake-model")


async def test_translate_speech_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/translate/speech",
        files={"audio": ("clip.wav", _TINY_WAV_HEADER, "audio/wav")},
        data={"target_language": "Hindi"},
    )
    assert response.status_code == 401


async def test_translate_speech_rejects_an_unsupported_audio_format(
    client: AsyncClient, real_session: _RealSession
) -> None:
    response = await client.post(
        "/v1/translate/speech",
        files={"audio": ("clip.xyz", b"not audio", "application/octet-stream")},
        data={"target_language": "Hindi"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AUDIO_UNUSABLE"


async def test_translate_speech_with_no_llm_configured_returns_503_not_a_crash(
    client: AsyncClient, real_session: _RealSession
) -> None:
    assert ai_factory.get_llm_gateway() is None, "this test assumes no real Gemini key is set"
    response = await client.post(
        "/v1/translate/speech",
        files={"audio": ("clip.wav", _TINY_WAV_HEADER, "audio/wav")},
        data={"target_language": "Hindi"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 503


async def test_translate_speech_with_mocked_llm_returns_transcription_and_translation(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import speech_translation_service

    fake_result = speech_translation_service._SpeechTranslationResult(
        transcribed_text="Where is the nearest railway station?",
        translated_text="निकटतम रेलवे स्टेशन कहाँ है?",
        transliteration="Nikatatam railway station kahaan hai?",
    )
    monkeypatch.setattr(
        speech_translation_service, "get_llm_gateway", lambda: _FakeGateway(fake_result)
    )

    response = await client.post(
        "/v1/translate/speech",
        files={"audio": ("clip.wav", _TINY_WAV_HEADER, "audio/wav")},
        data={"target_language": "Hindi"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["transcribed_text"] == "Where is the nearest railway station?"
    assert data["translated_text"] == "निकटतम रेलवे स्टेशन कहाँ है?"
