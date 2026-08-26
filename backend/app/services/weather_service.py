"""
Cache-first weather lookup for the F3 outdoor-activity flagging rule
(ARCHITECTURE_REVIEW.md H7). Never raises — a missing key or provider
failure returns None ("unknown"), which the business-rule validator
treats as "cannot verify, do not flag" rather than a hard failure
(CLAUDE.md §9's "external API failures degrade gracefully").
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from datetime import date as date_cls

from app.core.config import get_settings
from app.repositories.weather_repository import WeatherRepository, location_key
from app.services.weather_client import WeatherClient, WeatherProviderError

logger = logging.getLogger("app.services.weather")


def _is_adverse_in_entries(entries: list[dict], target_date: date_cls) -> bool | None:
    from app.services.weather_client import _is_adverse

    covered = False
    for entry in entries:
        ts = entry.get("dt")
        if ts is None:
            continue
        entry_date = datetime.fromtimestamp(ts, tz=UTC).date()
        if entry_date != target_date:
            continue
        covered = True
        for condition in entry.get("weather", []) or []:
            code = condition.get("id")
            if isinstance(code, int) and _is_adverse(code):
                return True
    return False if covered else None


async def check_adverse_weather(lat: float, lng: float, date_iso: str) -> bool | None:
    settings = get_settings()
    if settings.weather_api_key is None:
        return None

    key = location_key(lat, lng)
    repo = WeatherRepository()
    try:
        cached = await repo.get_cached_forecast(key)
    except Exception:  # noqa: BLE001 - cache read is best-effort, never blocks the check
        logger.warning("weather_cache_read_failed", exc_info=True)
        cached = None

    entries = cached
    if entries is None:
        client = WeatherClient(settings.weather_api_key.get_secret_value())
        try:
            entries = await client.get_forecast(lat, lng)
        except WeatherProviderError:
            logger.warning("weather_provider_call_failed", exc_info=True)
            return None
        try:
            await repo.upsert_forecast(key, entries)
        except Exception:  # noqa: BLE001 - cache write is best-effort
            logger.warning("weather_cache_write_failed", exc_info=True)

    target = date_cls.fromisoformat(date_iso)
    return _is_adverse_in_entries(entries, target)
