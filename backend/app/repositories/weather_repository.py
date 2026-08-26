"""Repository for `weather_cache` (DATABASE_SCHEMA.md §11) — no RLS (read
via backend service-role connection only, never client-exposed)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.repositories.base import Repository

_CACHE_TTL = timedelta(hours=3)


def location_key(lat: float, lng: float) -> str:
    return f"{round(lat, 2)},{round(lng, 2)}"


class WeatherRepository(Repository):
    async def get_cached_forecast(self, key: str) -> list[dict[str, Any]] | None:
        row = await self.fetchrow(
            "select forecast, expires_at from public.weather_cache where location_key = $1", key
        )
        if row is None:
            return None
        if row["expires_at"] < datetime.now(UTC):
            return None
        forecast = row["forecast"]
        return forecast if isinstance(forecast, list) else json.loads(forecast)

    async def upsert_forecast(self, key: str, forecast: list[dict[str, Any]]) -> None:
        expires_at = datetime.now(UTC) + _CACHE_TTL
        await self.fetchval(
            """
            insert into public.weather_cache (location_key, forecast, fetched_at, expires_at)
            values ($1, $2::jsonb, now(), $3)
            on conflict (location_key)
            do update set forecast = excluded.forecast, fetched_at = now(),
                          expires_at = excluded.expires_at
            returning location_key
            """,
            key,
            json.dumps(forecast),
            expires_at,
        )
