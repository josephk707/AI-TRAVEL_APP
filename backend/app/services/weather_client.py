"""
Real OpenWeatherMap client — the weather data source for the F3 outdoor-
activity flagging business rule (`ARCHITECTURE_REVIEW.md` H7, `AI_
ARCHITECTURE.md` §2 step 4, PRD §16). Mirrors `google_places_client.py`'s
pattern exactly: the only place in this codebase that talks to this
provider, one typed failure mode, results persisted through `weather_cache`
(`DATABASE_SCHEMA.md` §11) rather than re-fetched per request
(`AI_ARCHITECTURE.md` §12 cost control).
"""

from __future__ import annotations

import logging
from datetime import UTC

import httpx

logger = logging.getLogger("app.weather")

_BASE_URL = "https://api.openweathermap.org/data/2.5/forecast"
_DEFAULT_TIMEOUT_SECONDS = 8.0

# OpenWeatherMap's numeric condition codes, grouped into the ones that
# should trigger an "adverse weather" flag for an OUTDOOR itinerary item.
# Group 2xx=thunderstorm, 3xx=drizzle, 5xx=rain, 6xx=snow are all adverse;
# 7xx=atmosphere (fog/haze) at the more severe end; 800=clear/mostly clear
# is never adverse.
_ADVERSE_CODE_RANGES: list[tuple[int, int]] = [(200, 599), (700, 781)]


def _is_adverse(condition_code: int) -> bool:
    return any(low <= condition_code <= high for low, high in _ADVERSE_CODE_RANGES)


class WeatherProviderError(Exception):
    """Raised for any OpenWeatherMap failure — timeout, non-2xx, malformed
    response. Never leaks the API key (sent as a query param, but never
    echoed into this exception's message)."""


class WeatherClient:
    def __init__(self, api_key: str, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def get_forecast(self, lat: float, lng: float) -> list[dict]:
        """Returns the raw 5-day/3-hour forecast list (`data["list"]`) —
        each entry has `dt` (unix ts), `weather[0]["id"]` (condition code)."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    _BASE_URL,
                    params={"lat": lat, "lon": lng, "appid": self._api_key, "units": "metric"},
                )
        except httpx.TimeoutException as exc:
            raise WeatherProviderError("Weather request timed out.") from exc
        except httpx.HTTPError as exc:
            raise WeatherProviderError("Weather request failed.") from exc

        if response.status_code != 200:
            logger.warning("weather_non_200", extra={"status": response.status_code})
            raise WeatherProviderError(f"Weather provider returned HTTP {response.status_code}.")

        try:
            data = response.json()
        except ValueError as exc:
            raise WeatherProviderError("Weather provider returned a malformed response.") from exc

        entries = data.get("list")
        if not isinstance(entries, list):
            raise WeatherProviderError("Weather provider response had an unexpected shape.")
        return entries

    async def is_adverse_on_date(self, lat: float, lng: float, date_iso: str) -> bool | None:
        """Returns True if any 3-hour forecast slot on `date_iso` (YYYY-MM-DD)
        carries an adverse condition code, False if the date is covered and
        clear, or None if the date falls outside the 5-day forecast horizon
        (caller must treat None as "unknown", never as "not adverse")."""
        from datetime import date as date_cls
        from datetime import datetime

        target = date_cls.fromisoformat(date_iso)
        entries = await self.get_forecast(lat, lng)
        covered = False
        for entry in entries:
            ts = entry.get("dt")
            if ts is None:
                continue
            entry_date = datetime.fromtimestamp(ts, tz=UTC).date()
            if entry_date != target:
                continue
            covered = True
            weather_list = entry.get("weather", [])
            if isinstance(weather_list, list):
                for condition in weather_list:
                    code = condition.get("id")
                    if isinstance(code, int) and _is_adverse(code):
                        return True
        return False if covered else None
