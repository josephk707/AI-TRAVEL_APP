"""
Integration tests for /v1/heritage/* — F8 Heritage Narration RAG + F9
Visual Q&A — against the REAL Supabase project, using the REAL curated
heritage_content rows seeded by scripts/seed_heritage_content.py (not
mocked). The Gemini SDK boundary is monkeypatched for the LLM-composition
success paths (same discipline as test_trips_api.py); the "not configured"
paths exercise this environment's REAL current state (no GEMINI_API_KEY).

Run with:
  python scripts/run_live_tests.py tests/test_heritage_api.py -v
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import AsyncClient

from app.services.ai import factory as ai_factory
from app.services.ai.llm_gateway import EmbeddingResponse, LLMResponse

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and SUPABASE_URL and SERVICE_ROLE_KEY and ANON_KEY),
    reason="Full Supabase configuration not set — heritage API tests skipped",
)

# A real JPEG file signature (SOI + APP0 marker) followed by filler bytes —
# our own validate_image() only checks MIME type / non-empty / size, never
# parses actual pixel data, so this is sufficient without a full valid JPEG.
_TINY_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 32


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
    email = f"heritage-test-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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
        session = await _create_real_session(http, "heritage")
        try:
            yield session
        finally:
            await _delete_user(http, session.user_id)


class _FakeGateway:
    def __init__(self, parsed) -> None:
        self._parsed = parsed

    async def complete(self, messages, *, response_schema=None, config=None):
        return LLMResponse(text="{}", parsed=self._parsed, model="fake-model")

    async def complete_multimodal(self, messages, images, *, response_schema=None, config=None):
        return LLMResponse(text="{}", parsed=self._parsed, model="fake-model")

    async def complete_audio(self, *a, **k):  # pragma: no cover - unused here
        raise NotImplementedError

    async def embed(self, texts, *, dimensions, task_type="RETRIEVAL_DOCUMENT"):  # pragma: no cover
        return EmbeddingResponse(vectors=[[0.0] * dimensions for _ in texts], dimensions=dimensions)


async def _get_taj_mahal_poi_id(client: AsyncClient, auth_header: dict[str, str]) -> str:
    response = await client.get(
        "/v1/pois/search", params={"query": "Taj Mahal"}, headers=auth_header
    )
    return response.json()["data"][0]["id"]


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
async def test_narration_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.get(f"/v1/heritage/{uuid.uuid4()}/narration")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# F8 Narration
# ---------------------------------------------------------------------------
async def test_narration_returns_404_poi_not_covered_for_a_poi_with_no_heritage_content(
    client: AsyncClient, real_session: _RealSession
) -> None:
    # No heritage_content was ever seeded for a random POI id — proves the
    # "no fabricated narration" hard rule for real.
    response = await client.get(
        f"/v1/heritage/{uuid.uuid4()}/narration", headers=real_session.auth_header
    )
    assert response.status_code == 404


async def test_narration_with_no_llm_configured_returns_503_not_a_crash(
    client: AsyncClient, real_session: _RealSession
) -> None:
    assert ai_factory.get_llm_gateway() is None, "this test assumes no real Gemini key is set"
    poi_id = await _get_taj_mahal_poi_id(client, real_session.auth_header)

    response = await client.get(
        f"/v1/heritage/{poi_id}/narration", headers=real_session.auth_header
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "UPSTREAM_UNAVAILABLE"


async def test_narration_with_mocked_llm_composes_a_grounded_overview(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import narration_service

    poi_id = await _get_taj_mahal_poi_id(client, real_session.auth_header)
    fake_result = narration_service._NarrationSchema(
        narration="The Taj Mahal is an ivory-white marble mausoleum built by Shah Jahan."
    )
    monkeypatch.setattr(narration_service, "get_llm_gateway", lambda: _FakeGateway(fake_result))

    response = await client.get(
        f"/v1/heritage/{poi_id}/narration", headers=real_session.auth_header
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["poi_name"] == "Taj Mahal"
    assert data["confidence"] == "high"
    assert "Shah Jahan" in data["narration"]
    assert "Overview" in data["sources"]


# ---------------------------------------------------------------------------
# F9 Visual Q&A
# ---------------------------------------------------------------------------
async def test_photo_qa_rejects_unauthenticated_request(client: AsyncClient) -> None:
    response = await client.post(
        f"/v1/heritage/{uuid.uuid4()}/photo-qa",
        files={"image": ("photo.jpg", _TINY_JPEG, "image/jpeg")},
        data={"question": "What is this?"},
    )
    assert response.status_code == 401


async def test_photo_qa_rejects_an_unsupported_image_format(
    client: AsyncClient, real_session: _RealSession
) -> None:
    poi_id = await _get_taj_mahal_poi_id(client, real_session.auth_header)
    response = await client.post(
        f"/v1/heritage/{poi_id}/photo-qa",
        files={"image": ("photo.gif", b"GIF89a", "image/gif")},
        data={"question": "What is this?"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IMAGE_UNUSABLE"


async def test_photo_qa_with_no_llm_configured_returns_503_not_a_crash(
    client: AsyncClient, real_session: _RealSession
) -> None:
    assert ai_factory.get_llm_gateway() is None, "this test assumes no real Gemini key is set"
    poi_id = await _get_taj_mahal_poi_id(client, real_session.auth_header)

    response = await client.post(
        f"/v1/heritage/{poi_id}/photo-qa",
        files={"image": ("photo.jpg", _TINY_JPEG, "image/jpeg")},
        data={"question": "What is this dome made of?"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 503


async def test_photo_qa_with_mocked_llm_returns_a_grounded_answer(
    client: AsyncClient, real_session: _RealSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import photo_qa_service

    poi_id = await _get_taj_mahal_poi_id(client, real_session.auth_header)
    fake_result = photo_qa_service._PhotoQaResult(
        answer="That's the main marble dome of the Taj Mahal.", matches_source=True
    )
    monkeypatch.setattr(photo_qa_service, "get_llm_gateway", lambda: _FakeGateway(fake_result))

    response = await client.post(
        f"/v1/heritage/{poi_id}/photo-qa",
        files={"image": ("photo.jpg", _TINY_JPEG, "image/jpeg")},
        data={"question": "What is this dome made of?"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["grounded"] is True
    assert data["confidence"] == "high"
    assert "dome" in data["answer"].lower()
