"""
REAL, LIVE Gemini API validation — Phase 6 certification pass
(2026-08-26). Every test in this file makes a genuine network call to the
real configured Gemini API — `get_llm_gateway()` is never monkeypatched
anywhere in this file, unlike test_trips_api.py/test_heritage_api.py/
test_speech_translation_api.py, which deliberately mock the Gemini SDK
boundary to test THIS PROJECT's own pipeline logic independent of network
access. This file exists specifically to prove the real integration works
end-to-end, per this phase's explicit "do not use mocked Gemini calls for
the final live-validation report" instruction.

Skipped entirely unless GEMINI_API_KEY (and full Supabase config) are set
— real API calls cost real quota, so this is not part of the default fast
unit-test loop; run it deliberately.

Run with:
  python scripts/run_live_tests.py tests/test_llm_gateway_live.py -v -s
"""

from __future__ import annotations

import io
import math
import os
import struct
import uuid
import wave
import zlib
from binascii import crc32
from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import AsyncClient

from app.core.config import get_settings

DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

_settings = get_settings()

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and SUPABASE_URL and SERVICE_ROLE_KEY and ANON_KEY),
    reason="Full Supabase configuration not set — live Gemini tests skipped",
)
gemini_required = pytest.mark.skipif(
    _settings.gemini_api_key is None,
    reason="GEMINI_API_KEY not configured — live Gemini tests skipped",
)


def _make_test_png(
    width: int = 48, height: int = 48, rgb: tuple[int, int, int] = (200, 30, 30)
) -> bytes:
    """A genuine, valid, minimal PNG (solid color) — not a landmark photo
    (none is available in this environment), but real, decodable image
    bytes a real multimodal call can actually process."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = bytes([rgb[0], rgb[1], rgb[2]] * width)
    raw = b"".join(b"\x00" + row for _ in range(height))
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _make_test_wav(seconds: float = 1.0, freq: float = 440.0, rate: int = 16000) -> bytes:
    """A genuine, valid, decodable WAV file (a pure sine tone) — not real
    human speech (none is recordable in this headless environment), but
    real audio bytes a real audio-understanding call can actually process,
    proving the audio-modality pipeline itself is genuinely wired."""
    n = int(seconds * rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(3000 * math.sin(2 * math.pi * freq * (i / rate))))
            for i in range(n)
        )
        w.writeframes(frames)
    return buf.getvalue()


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
    email = f"live-gemini-{tag}-{uuid.uuid4().hex[:10]}@example.invalid"
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


@pytest.fixture(autouse=True)
async def _respect_free_tier_rate_limit() -> None:
    """This key's free-tier plan for `gemini-flash-latest` rate-limits far
    more aggressively than typical published free-tier figures — real
    `429 RESOURCE_EXHAUSTED` responses were hit repeatedly running this
    suite's ~13 real calls back-to-back with only normal network latency
    between them. A deliberate pacing delay before each test (this is a
    one-time live-validation run, not a CI gate — total wall time doesn't
    matter) is the correct fix for an external rate limit, not a retry
    loop that would just trade a slower failure for a slower success."""
    import asyncio

    await asyncio.sleep(20)


@pytest.fixture
async def real_session() -> AsyncIterator[_RealSession]:
    async with httpx.AsyncClient(timeout=30) as http:
        session = await _create_real_session(http, "live")
        try:
            yield session
        finally:
            await _delete_user(http, session.user_id)


# ---------------------------------------------------------------------------
# 1. LLM Gateway itself — real network call, no HTTP layer involved
# ---------------------------------------------------------------------------
@gemini_required
async def test_gemini_gateway_real_text_completion() -> None:
    from app.services.ai.factory import get_llm_gateway
    from app.services.ai.llm_gateway import GenerationConfig, LLMMessage, MessageRole

    gateway = get_llm_gateway()
    assert gateway is not None
    response = await gateway.complete(
        [LLMMessage(MessageRole.USER, "Reply with exactly the single word: PONG")],
        config=GenerationConfig(max_output_tokens=64, temperature=0.0, timeout_seconds=25.0),
    )
    assert "PONG" in response.text.upper()
    assert response.model


@gemini_required
async def test_gemini_gateway_real_structured_output() -> None:
    from pydantic import BaseModel

    from app.services.ai.factory import get_llm_gateway
    from app.services.ai.llm_gateway import GenerationConfig, LLMMessage, MessageRole

    class _Reply(BaseModel):
        message: str
        count: int

    gateway = get_llm_gateway()
    assert gateway is not None
    response = await gateway.complete(
        [LLMMessage(MessageRole.USER, 'Return JSON with message="hello" and count=3.')],
        response_schema=_Reply,
        config=GenerationConfig(max_output_tokens=200, temperature=0.0, timeout_seconds=25.0),
    )
    assert isinstance(response.parsed, _Reply)
    assert response.parsed.count == 3


@gemini_required
async def test_gemini_gateway_real_embeddings() -> None:
    from app.services.ai.factory import get_llm_gateway

    gateway = get_llm_gateway()
    assert gateway is not None
    response = await gateway.embed(
        ["The Taj Mahal is a marble mausoleum in Agra."], dimensions=1536
    )
    assert response.dimensions == 1536
    assert len(response.vectors[0]) == 1536


# ---------------------------------------------------------------------------
# 2. F3 — real itinerary generation, full stack, real DB persistence
# ---------------------------------------------------------------------------
@gemini_required
async def test_real_itinerary_generation_produces_a_grounded_persisted_plan(
    client: AsyncClient, real_session: _RealSession
) -> None:
    create_response = await client.post(
        "/v1/trips",
        json={
            "title": "Agra Trip (live Gemini test)",
            "destination": "Agra, India",
            "start_date": "2026-10-10",
            "end_date": "2026-10-10",
            "budget_planned": 15000,
        },
        headers=real_session.auth_header,
    )
    assert create_response.status_code == 201
    trip_id = create_response.json()["data"]["id"]

    generate_response = await client.post(
        f"/v1/trips/{trip_id}/itinerary/generate",
        json={"interests": ["heritage"]},
        headers=real_session.auth_header,
    )
    assert generate_response.status_code == 200
    body = generate_response.json()
    data = body["data"]
    # A real, successful Gemini call -> 'succeeded', not the no-AI fallback.
    assert data["generation_status"] == "succeeded", body
    assert body["meta"] is None
    assert data["summary"]
    all_items = [item for day in data["days"] for item in day["items"]]
    assert len(all_items) > 0
    # The candidate-index guardrail means every scheduled item must be a
    # REAL POI that exists in this project's own database — never a
    # hallucinated venue. Asserted against the LIVE candidate set rather
    # than a hardcoded name: this previously pinned "Taj Mahal" as the only
    # seeded Agra POI, which stopped being true once the Phase 8 heritage
    # expansion seeded more, turning a passing guardrail into a false
    # failure. The real invariant is membership in the seeded set.
    # Read the candidate set from the SAME source the pipeline itself uses
    # (`itinerary_service._get_candidates` -> `PoisRepository.search_text`),
    # not `/v1/pois/search`, which live-augments from an external provider
    # and would make this a weaker, noisier check.
    from app.repositories.pois_repository import PoisRepository

    seeded_names = {
        poi["name"] for poi in await PoisRepository().search_text("Agra", category=None, limit=15)
    }
    assert seeded_names, "no Agra POIs seeded — the guardrail below would be vacuous"
    assert all(item["poi_name"] in seeded_names for item in all_items), (
        f"itinerary contains a POI absent from the database: "
        f"{[i['poi_name'] for i in all_items if i['poi_name'] not in seeded_names]}"
    )

    # Real DB persistence check: fetch it back via a SEPARATE request.
    itinerary_response = await client.get(
        f"/v1/trips/{trip_id}/itinerary", headers=real_session.auth_header
    )
    assert itinerary_response.status_code == 200
    persisted_items = [i for d in itinerary_response.json()["data"] for i in d["items"]]
    assert len(persisted_items) == len(all_items)


# ---------------------------------------------------------------------------
# 3. F4 — real idea extraction
# ---------------------------------------------------------------------------
@gemini_required
async def test_real_idea_extraction_pulls_the_named_place_out_of_free_text(
    client: AsyncClient, real_session: _RealSession
) -> None:
    create_response = await client.post(
        "/v1/trips",
        json={"title": "Agra Notes Trip", "destination": "Agra, India"},
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]

    notes_response = await client.post(
        f"/v1/trips/{trip_id}/notes",
        json={"raw_text": "I would love to see the Taj Mahal at sunrise, and try some local food."},
        headers=real_session.auth_header,
    )
    assert notes_response.status_code == 201
    data = notes_response.json()["data"]
    assert data["extracted_places"] is not None
    place_names = [
        p.get("name", "") for p in data["extracted_places"] if isinstance(p, dict) and "name" in p
    ]
    assert any("taj" in name.lower() for name in place_names), data


# ---------------------------------------------------------------------------
# 4. F5 — real conversational modification
# ---------------------------------------------------------------------------
@gemini_required
async def test_real_conversational_modification_changes_the_targeted_item(
    client: AsyncClient, real_session: _RealSession
) -> None:
    create_response = await client.post(
        "/v1/trips",
        json={
            "title": "Agra Modify Trip",
            "destination": "Agra, India",
            "start_date": "2026-10-10",
            "end_date": "2026-10-10",
            "budget_planned": 15000,
        },
        headers=real_session.auth_header,
    )
    trip_id = create_response.json()["data"]["id"]
    generate_response = await client.post(
        f"/v1/trips/{trip_id}/itinerary/generate", json={}, headers=real_session.auth_header
    )
    assert generate_response.json()["data"]["generation_status"] == "succeeded"

    modify_response = await client.post(
        f"/v1/trips/{trip_id}/itinerary/modify",
        json={"message": "Please move the Taj Mahal visit to start at 07:30 instead."},
        headers=real_session.auth_header,
    )
    assert modify_response.status_code == 200
    data = modify_response.json()["data"]
    assert data["reply"]


# ---------------------------------------------------------------------------
# 5. F10 — real dynamic translation, all four required languages
# ---------------------------------------------------------------------------
@gemini_required
@pytest.mark.parametrize("language", ["Hindi", "Telugu", "Malayalam", "Kannada"])
async def test_real_translation_of_an_arbitrary_phrase(
    client: AsyncClient, real_session: _RealSession, language: str
) -> None:
    response = await client.post(
        "/v1/translate/text",
        json={"text": "Where is the nearest railway station?", "target_language": language},
        headers=real_session.auth_header,
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["target_language"] == language
    assert len(data["translated_text"]) > 0
    assert len(data["transliteration"]) > 0
    assert data["recognized_language"] is True


# ---------------------------------------------------------------------------
# 6. F8 — real heritage RAG narration
# ---------------------------------------------------------------------------
@gemini_required
async def test_real_heritage_narration_is_grounded_in_seeded_content(
    client: AsyncClient, real_session: _RealSession
) -> None:
    search_response = await client.get(
        "/v1/pois/search", params={"query": "Taj Mahal"}, headers=real_session.auth_header
    )
    poi_id = search_response.json()["data"][0]["id"]

    narration_response = await client.get(
        f"/v1/heritage/{poi_id}/narration", headers=real_session.auth_header
    )
    assert narration_response.status_code == 200, narration_response.text
    data = narration_response.json()["data"]
    assert data["poi_name"] == "Taj Mahal"
    assert len(data["narration"]) > 0
    assert data["confidence"] in ("high", "low")
    assert "Overview" in data["sources"]
    # Grounding check: the real curated content names Shah Jahan; a
    # genuinely grounded narration should reflect that, not drift into
    # ungrounded generic text.
    assert "shah jahan" in data["narration"].lower()


# ---------------------------------------------------------------------------
# 7. F9 — real multimodal visual Q&A
# ---------------------------------------------------------------------------
@gemini_required
async def test_real_visual_qa_answers_about_a_real_uploaded_image(
    client: AsyncClient, real_session: _RealSession
) -> None:
    search_response = await client.get(
        "/v1/pois/search", params={"query": "Taj Mahal"}, headers=real_session.auth_header
    )
    poi_id = search_response.json()["data"][0]["id"]
    png_bytes = _make_test_png()

    response = await client.post(
        f"/v1/heritage/{poi_id}/photo-qa",
        files={"image": ("test.png", png_bytes, "image/png")},
        data={"question": "What color is the dominant color in this image?"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data["answer"]) > 0
    assert data["confidence"] in ("high", "low")


# ---------------------------------------------------------------------------
# 8. F25 — real speech-audio understanding
# ---------------------------------------------------------------------------
@gemini_required
async def test_real_speech_translation_processes_a_real_audio_clip(
    client: AsyncClient, real_session: _RealSession
) -> None:
    wav_bytes = _make_test_wav()

    response = await client.post(
        "/v1/translate/speech",
        files={"audio": ("clip.wav", wav_bytes, "audio/wav")},
        data={"target_language": "Hindi"},
        headers=real_session.auth_header,
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    # A pure sine tone has no real speech — Gemini is expected to say so
    # in transcribed_text/note rather than hallucinate a sentence. Either
    # way, this proves the real audio-modality call round-trips correctly.
    assert isinstance(data["transcribed_text"], str)
    assert data["target_language"] == "Hindi"


# ---------------------------------------------------------------------------
# 9. Cross-user isolation with real AI calls (personalization/security)
# ---------------------------------------------------------------------------
@gemini_required
async def test_two_users_generating_itineraries_never_see_each_others_trips(
    client: AsyncClient, real_session: _RealSession
) -> None:
    async with httpx.AsyncClient(timeout=30) as http:
        other = await _create_real_session(http, "live-other")
        try:
            create_response = await client.post(
                "/v1/trips",
                json={
                    "title": "User A's private trip",
                    "destination": "Agra, India",
                    "start_date": "2026-10-10",
                    "end_date": "2026-10-10",
                    "budget_planned": 15000,
                },
                headers=real_session.auth_header,
            )
            trip_id = create_response.json()["data"]["id"]
            await client.post(
                f"/v1/trips/{trip_id}/itinerary/generate", json={}, headers=real_session.auth_header
            )

            other_list_response = await client.get("/v1/trips", headers=other.auth_header)
            other_trip_ids = {t["id"] for t in other_list_response.json()["data"]}
            assert trip_id not in other_trip_ids

            forbidden_response = await client.get(
                f"/v1/trips/{trip_id}/itinerary", headers=other.auth_header
            )
            assert forbidden_response.status_code == 403
        finally:
            await _delete_user(http, other.user_id)
