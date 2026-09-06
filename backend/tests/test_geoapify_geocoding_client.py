"""
Unit tests for app/services/geoapify_geocoding_client.py — request shaping
and failure handling against httpx's `MockTransport` (no network, no key,
no cost), mirroring tests/test_geoapify_places_client.py.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.geoapify_geocoding_client import GeoapifyGeocodingClient
from app.services.google_places_client import PlacesProviderError


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:  # noqa: ANN001
    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def fake_async_client(**kwargs):  # noqa: ANN003
        kwargs["transport"] = transport
        return real_async_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)


def _feature(**props: object) -> dict:
    return {"type": "Feature", "properties": props}


async def test_geocode_sends_text_bias_and_key_and_normalizes_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "features": [
                    _feature(
                        name="Humayun's Tomb",
                        formatted="Humayun's Tomb, Delhi, India",
                        lat=28.5933,
                        lon=77.2506,
                        place_id="pid-1",
                        result_type="amenity",
                        rank={"confidence": 1, "match_type": "full_match"},
                        city="Delhi",
                        state="Delhi",
                        country="India",
                    ),
                    # A feature with no coordinates is skipped, never surfaced.
                    _feature(name="broken", place_id="pid-2"),
                ]
            },
        )

    _patch_transport(monkeypatch, handler)
    client = GeoapifyGeocodingClient(api_key="fake-test-key-not-real")

    results = await client.geocode("Humayun's Tomb, Delhi", bias_lat=28.61, bias_lng=77.21)

    assert "text=Humayun" in captured["url"]
    assert "bias=proximity%3A77.21%2C28.61" in captured["url"]
    assert "apiKey=fake-test-key-not-real" in captured["url"]
    assert results == [
        {
            "name": "Humayun's Tomb",
            "formatted": "Humayun's Tomb, Delhi, India",
            "lat": 28.5933,
            "lng": 77.2506,
            "place_id": "pid-1",
            "result_type": "amenity",
            "confidence": 1.0,
            "match_type": "full_match",
            "city": "Delhi",
            "region": "Delhi",
            "country": "India",
        }
    ]


async def test_geocode_omits_bias_when_no_centre_is_known(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"features": []})

    _patch_transport(monkeypatch, handler)
    results = await GeoapifyGeocodingClient(api_key="k").geocode("Anywhere")

    assert results == []
    assert "bias=" not in captured["url"]


@pytest.mark.parametrize("status", [401, 429, 500])
async def test_geocode_raises_provider_error_on_non_200(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(status, json={}))

    with pytest.raises(PlacesProviderError):
        await GeoapifyGeocodingClient(api_key="k").geocode("Delhi")


async def test_geocode_raises_provider_error_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    _patch_transport(monkeypatch, handler)

    with pytest.raises(PlacesProviderError):
        await GeoapifyGeocodingClient(api_key="k").geocode("Delhi")


async def test_geocode_raises_provider_error_on_unexpected_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(200, json={"nope": 1}))

    with pytest.raises(PlacesProviderError):
        await GeoapifyGeocodingClient(api_key="k").geocode("Delhi")
