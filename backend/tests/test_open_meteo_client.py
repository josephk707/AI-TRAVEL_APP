"""Unit tests for app/services/open_meteo_client.py — request shaping and
failure handling against a fake HTTP transport, no real network call, no
API key needed (matches this client's own real, keyless design)."""

from __future__ import annotations

import httpx
import pytest

from app.services.open_meteo_client import (
    OpenMeteoClient,
    WeatherProviderError,
    describe_weather_code,
)


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:  # noqa: ANN001
    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def fake_async_client(**kwargs):  # noqa: ANN003
        kwargs["transport"] = transport
        return real_async_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_async_client)


_VALID_RESPONSE = {
    "current": {
        "temperature_2m": 28.4,
        "relative_humidity_2m": 55,
        "weather_code": 2,
        "wind_speed_10m": 9.1,
        "is_day": 1,
    },
    "daily": {
        "time": ["2026-08-28", "2026-08-29"],
        "temperature_2m_max": [33.1, 32.0],
        "temperature_2m_min": [25.0, 24.5],
        "weather_code": [2, 61],
        "precipitation_probability_max": [10, 60],
    },
}


async def test_get_forecast_sends_lat_lng_and_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=_VALID_RESPONSE)

    _patch_transport(monkeypatch, handler)
    client = OpenMeteoClient()

    data = await client.get_forecast(lat=27.17, lng=78.04)

    assert data["current"]["temperature_2m"] == 28.4
    assert "latitude=27.17" in captured["url"]
    assert "longitude=78.04" in captured["url"]
    assert "apiKey" not in captured["url"] and "api_key" not in captured["url"].lower()


async def test_get_forecast_raises_weather_provider_error_on_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(400, json={"error": "bad"}))
    client = OpenMeteoClient()

    with pytest.raises(WeatherProviderError):
        await client.get_forecast(lat=27.17, lng=78.04)


async def test_get_forecast_raises_weather_provider_error_on_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(200, content=b"not json"))
    client = OpenMeteoClient()

    with pytest.raises(WeatherProviderError):
        await client.get_forecast(lat=27.17, lng=78.04)


async def test_get_forecast_raises_weather_provider_error_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")

    _patch_transport(monkeypatch, handler)
    client = OpenMeteoClient()

    with pytest.raises(WeatherProviderError):
        await client.get_forecast(lat=27.17, lng=78.04)


async def test_get_forecast_raises_on_unexpected_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(200, json={"nope": True}))
    client = OpenMeteoClient()

    with pytest.raises(WeatherProviderError):
        await client.get_forecast(lat=27.17, lng=78.04)


def test_describe_weather_code_covers_common_codes() -> None:
    assert describe_weather_code(0) == "Clear sky"
    assert describe_weather_code(61) == "Slight rain"
    assert describe_weather_code(95) == "Thunderstorm"


def test_describe_weather_code_handles_unknown_and_none() -> None:
    assert describe_weather_code(None) == "Unknown"
    assert describe_weather_code(9999) == "Unknown"
