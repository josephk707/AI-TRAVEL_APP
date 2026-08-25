"""
Unit tests for app/services/google_places_client.py — request shaping and
failure handling, exercised against a fake HTTP transport (httpx's own
`MockTransport`, not a real network call — no API key, no cost, no
external dependency). Every failure mode this client documents is proven
here: timeout, non-200, and a malformed (non-JSON) response all become one
typed `PlacesProviderError`, never a raw httpx exception leaking upward.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.google_places_client import GooglePlacesClient, PlacesProviderError


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:  # noqa: ANN001
    """Routes every httpx.AsyncClient this module constructs through a fake
    in-process transport instead of the real network."""
    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def fake_async_client(**kwargs):  # noqa: ANN003
        kwargs["transport"] = transport
        return real_async_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)


async def test_search_text_sends_the_documented_request_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "places": [
                    {
                        "id": "ChIJ_test123",
                        "displayName": {"text": "Test Place"},
                        "formattedAddress": "123 Test St",
                        "location": {"latitude": 27.17, "longitude": 78.04},
                        "types": ["tourist_attraction"],
                    }
                ]
            },
        )

    _patch_transport(monkeypatch, handler)
    client = GooglePlacesClient(api_key="fake-test-key-not-real")

    results = await client.search_text("Taj Mahal")

    assert results[0]["id"] == "ChIJ_test123"
    assert captured["headers"]["x-goog-api-key"] == "fake-test-key-not-real"
    assert "x-goog-fieldmask" in captured["headers"]
    assert "places:searchText" in captured["url"]
    assert b"Taj Mahal" in captured["body"]


async def test_search_text_raises_places_provider_error_on_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(403, json={"error": "denied"}))
    client = GooglePlacesClient(api_key="fake-test-key-not-real")

    with pytest.raises(PlacesProviderError):
        await client.search_text("anything")


async def test_search_text_raises_places_provider_error_on_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(200, content=b"not json"))
    client = GooglePlacesClient(api_key="fake-test-key-not-real")

    with pytest.raises(PlacesProviderError):
        await client.search_text("anything")


async def test_search_text_raises_places_provider_error_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")

    _patch_transport(monkeypatch, handler)
    client = GooglePlacesClient(api_key="fake-test-key-not-real")

    with pytest.raises(PlacesProviderError):
        await client.search_text("anything")


async def test_search_nearby_sends_a_circle_location_restriction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"places": []})

    _patch_transport(monkeypatch, handler)
    client = GooglePlacesClient(api_key="fake-test-key-not-real")

    results = await client.search_nearby(lat=27.17, lng=78.04, radius_m=2000)

    assert results == []
    assert b"locationRestriction" in captured["body"]
    assert b"circle" in captured["body"]


async def test_search_response_with_unexpected_shape_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(200, json={"places": "nope"}))
    client = GooglePlacesClient(api_key="fake-test-key-not-real")

    with pytest.raises(PlacesProviderError):
        await client.search_text("anything")


async def test_get_place_returns_the_raw_place_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(
        monkeypatch, lambda request: httpx.Response(200, json={"id": "ChIJ_x", "displayName": {}})
    )
    client = GooglePlacesClient(api_key="fake-test-key-not-real")

    result = await client.get_place("ChIJ_x")

    assert result["id"] == "ChIJ_x"


async def test_get_place_raises_places_provider_error_on_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(404, json={}))
    client = GooglePlacesClient(api_key="fake-test-key-not-real")

    with pytest.raises(PlacesProviderError):
        await client.get_place("does-not-exist")
