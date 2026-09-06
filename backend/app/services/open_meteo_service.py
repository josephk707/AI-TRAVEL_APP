"""Business logic for GET /v1/weather — Maps Integration phase. Thin
mapping layer over open_meteo_client.py, per CLAUDE.md §7 (route handlers
stay thin, business/mapping logic lives here)."""

from __future__ import annotations

from typing import Any

from app.core.exceptions import UpstreamUnavailableError
from app.services.open_meteo_client import (
    OpenMeteoClient,
    WeatherProviderError,
    describe_weather_code,
)


def _map_current(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "temperature_c": raw["temperature_2m"],
        "condition_code": raw["weather_code"],
        "condition": describe_weather_code(raw.get("weather_code")),
        "humidity_percent": raw.get("relative_humidity_2m"),
        "wind_speed_kmh": raw.get("wind_speed_10m"),
        "is_day": bool(raw.get("is_day", 1)),
    }


def _map_daily(raw: dict[str, Any]) -> list[dict[str, Any]]:
    dates = raw.get("time", [])
    max_temps = raw.get("temperature_2m_max", [])
    min_temps = raw.get("temperature_2m_min", [])
    codes = raw.get("weather_code", [])
    precip = raw.get("precipitation_probability_max", [])

    entries = []
    for i, date in enumerate(dates):
        entries.append(
            {
                "date": date,
                "temperature_max_c": max_temps[i],
                "temperature_min_c": min_temps[i],
                "condition_code": codes[i],
                "condition": describe_weather_code(codes[i] if i < len(codes) else None),
                "precipitation_probability_percent": precip[i] if i < len(precip) else None,
            }
        )
    return entries


async def get_weather(lat: float, lng: float) -> dict[str, Any]:
    """Real, live Open-Meteo call — no cache, no API key required (see
    open_meteo_client.py). Raises UpstreamUnavailableError (503) on any
    provider failure — CLAUDE.md §9 graceful degradation: the client
    surfaces a real, typed error state rather than fabricating a forecast."""
    client = OpenMeteoClient()
    try:
        raw = await client.get_forecast(lat, lng)
    except WeatherProviderError as exc:
        raise UpstreamUnavailableError(
            "Weather is temporarily unavailable — please try again in a moment.",
            details={"code": "WEATHER_PROVIDER_ERROR"},
        ) from exc

    try:
        current = _map_current(raw["current"])
        daily = _map_daily(raw["daily"])
    except (KeyError, IndexError) as exc:
        raise UpstreamUnavailableError(
            "Weather is temporarily unavailable — please try again in a moment.",
            details={"code": "WEATHER_RESPONSE_UNEXPECTED_SHAPE"},
        ) from exc

    return {"lat": lat, "lng": lng, "current": current, "daily": daily}
