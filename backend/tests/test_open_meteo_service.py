"""Unit tests for app/services/open_meteo_service.py's mapping/error logic
— exercised with a monkeypatched client, no real network."""

from __future__ import annotations

import pytest

from app.core.exceptions import UpstreamUnavailableError
from app.services import open_meteo_service
from app.services.open_meteo_client import OpenMeteoClient, WeatherProviderError

_RAW_RESPONSE = {
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


async def test_get_weather_maps_current_and_daily_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_forecast(self, lat, lng, forecast_days=5):  # noqa: ANN001
        return _RAW_RESPONSE

    monkeypatch.setattr(OpenMeteoClient, "get_forecast", fake_get_forecast)

    result = await open_meteo_service.get_weather(27.17, 78.04)

    assert result["lat"] == 27.17
    assert result["current"]["temperature_c"] == 28.4
    assert result["current"]["condition"] == "Partly cloudy"
    assert result["current"]["is_day"] is True
    assert len(result["daily"]) == 2
    assert result["daily"][0]["date"] == "2026-08-28"
    assert result["daily"][1]["condition"] == "Slight rain"
    assert result["daily"][1]["precipitation_probability_percent"] == 60


async def test_get_weather_raises_upstream_unavailable_on_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_get_forecast(self, lat, lng, forecast_days=5):  # noqa: ANN001
        raise WeatherProviderError("simulated outage")

    monkeypatch.setattr(OpenMeteoClient, "get_forecast", failing_get_forecast)

    with pytest.raises(UpstreamUnavailableError):
        await open_meteo_service.get_weather(27.17, 78.04)


async def test_get_weather_raises_upstream_unavailable_on_missing_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_forecast(self, lat, lng, forecast_days=5):  # noqa: ANN001
        return {"current": {}, "daily": {}}

    monkeypatch.setattr(OpenMeteoClient, "get_forecast", fake_get_forecast)

    with pytest.raises(UpstreamUnavailableError):
        await open_meteo_service.get_weather(27.17, 78.04)
