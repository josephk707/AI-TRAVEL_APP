"""
Real Open-Meteo client — Maps Integration phase, user-facing destination
weather (current conditions + short forecast), shown in the mobile app
(PoiDetailScreen). Deliberately separate from weather_client.py/
weather_service.py, which are a DIFFERENT, pre-existing, internal-only
integration (OpenWeatherMap, gated behind WEATHER_API_KEY) powering the F3
outdoor-activity adverse-weather itinerary flag — that pipeline is
untouched by this phase.

Open-Meteo's free/non-commercial tier requires no API key (per
https://open-meteo.com/en/pricing — "Free Access for Non-Commercial Use"),
so there is no secret to configure or protect here; this client is safe
to exist unconditionally, unlike every other provider client in this
codebase.

Same one-typed-failure-mode contract as every other provider client here
(CLAUDE.md §9): any failure — timeout, non-2xx, malformed JSON, missing
expected fields — becomes `WeatherProviderError`, never a raw httpx
exception leaking upward.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("app.open_meteo")

_BASE_URL = "https://api.open-meteo.com/v1/forecast"
_DEFAULT_TIMEOUT_SECONDS = 8.0

_CURRENT_FIELDS = "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,is_day"
_DAILY_FIELDS = "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max"

# WMO weather-interpretation codes (Open-Meteo's own documented mapping,
# https://open-meteo.com/en/docs — "WMO Weather interpretation codes") —
# grouped down to a short human-readable description per code. Kept as a
# real, complete, documented table, not a guess.
WMO_CODE_DESCRIPTIONS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def describe_weather_code(code: int | None) -> str:
    if code is None:
        return "Unknown"
    return WMO_CODE_DESCRIPTIONS.get(code, "Unknown")


class WeatherProviderError(Exception):
    """Raised for any Open-Meteo failure — timeout, non-2xx, malformed or
    unexpectedly-shaped response."""


class OpenMeteoClient:
    def __init__(self, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    async def get_forecast(self, lat: float, lng: float, forecast_days: int = 5) -> dict[str, Any]:
        """Returns the raw parsed JSON response — current conditions plus
        a `forecast_days`-day daily outlook. Mapping into this app's own
        response schema happens in open_meteo_service.py."""
        params: dict[str, str | int | float] = {
            "latitude": lat,
            "longitude": lng,
            "current": _CURRENT_FIELDS,
            "daily": _DAILY_FIELDS,
            "forecast_days": forecast_days,
            "timezone": "auto",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(_BASE_URL, params=params)
        except httpx.TimeoutException as exc:
            raise WeatherProviderError("Open-Meteo request timed out.") from exc
        except httpx.HTTPError as exc:
            raise WeatherProviderError("Open-Meteo request failed.") from exc

        if response.status_code != 200:
            logger.warning("open_meteo_non_200", extra={"status": response.status_code})
            raise WeatherProviderError(f"Open-Meteo returned HTTP {response.status_code}.")

        try:
            data = response.json()
        except ValueError as exc:
            raise WeatherProviderError("Open-Meteo returned a malformed response.") from exc

        if not isinstance(data, dict) or "current" not in data or "daily" not in data:
            raise WeatherProviderError("Open-Meteo response had an unexpected shape.")
        return data
