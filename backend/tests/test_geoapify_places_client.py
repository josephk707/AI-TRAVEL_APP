"""
Unit tests for app/services/geoapify_places_client.py — request shaping
and failure handling, exercised against a fake HTTP transport (httpx's own
`MockTransport`, not a real network call — no API key, no cost, no
external dependency). Mirrors tests/test_google_places_client.py's
structure exactly, since the two clients share the same contract.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.geoapify_places_client import GeoapifyPlacesClient
from app.services.google_places_client import PlacesProviderError


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:  # noqa: ANN001
    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def fake_async_client(**kwargs):  # noqa: ANN003
        kwargs["transport"] = transport
        return real_async_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)


async def test_search_nearby_sends_a_circle_filter_and_the_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "place_id": "geo_test123",
                            "name": "Test Place",
                            "lat": 27.17,
                            "lon": 78.04,
                            "formatted": "1 Test St",
                            "categories": ["tourism.sights"],
                        },
                    }
                ],
            },
        )

    _patch_transport(monkeypatch, handler)
    client = GeoapifyPlacesClient(api_key="fake-test-key-not-real")

    results = await client.search_nearby(lat=27.17, lng=78.04, radius_m=2000)

    assert results[0]["properties"]["place_id"] == "geo_test123"
    assert "filter=circle" in captured["url"]
    assert "apiKey=fake-test-key-not-real" in captured["url"]
    assert "bias=proximity" in captured["url"]


async def test_search_nearby_narrows_categories_for_a_known_app_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"features": []})

    _patch_transport(monkeypatch, handler)
    client = GeoapifyPlacesClient(api_key="fake-test-key-not-real")

    await client.search_nearby(lat=27.17, lng=78.04, radius_m=2000, category="restaurant")

    assert "catering" in captured["url"]


async def test_search_nearby_raises_places_provider_error_on_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(403, json={"error": "denied"}))
    client = GeoapifyPlacesClient(api_key="fake-test-key-not-real")

    with pytest.raises(PlacesProviderError):
        await client.search_nearby(lat=27.17, lng=78.04, radius_m=2000)


async def test_search_nearby_raises_places_provider_error_on_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(200, content=b"not json"))
    client = GeoapifyPlacesClient(api_key="fake-test-key-not-real")

    with pytest.raises(PlacesProviderError):
        await client.search_nearby(lat=27.17, lng=78.04, radius_m=2000)


async def test_search_nearby_raises_places_provider_error_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")

    _patch_transport(monkeypatch, handler)
    client = GeoapifyPlacesClient(api_key="fake-test-key-not-real")

    with pytest.raises(PlacesProviderError):
        await client.search_nearby(lat=27.17, lng=78.04, radius_m=2000)


async def test_search_nearby_response_with_unexpected_shape_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(200, json={"features": "nope"}))
    client = GeoapifyPlacesClient(api_key="fake-test-key-not-real")

    with pytest.raises(PlacesProviderError):
        await client.search_nearby(lat=27.17, lng=78.04, radius_m=2000)
