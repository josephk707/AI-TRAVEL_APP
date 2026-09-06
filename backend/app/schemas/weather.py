"""Request/response schemas for GET /v1/weather — Maps Integration phase,
Open-Meteo-backed destination weather (current + short forecast). See
app/services/open_meteo_client.py's module docstring for why this is a
separate, new, user-facing capability from the pre-existing internal
weather_service.py."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WeatherQuery(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class CurrentWeather(BaseModel):
    temperature_c: float
    condition_code: int
    condition: str
    humidity_percent: float | None
    wind_speed_kmh: float | None
    is_day: bool


class DailyForecastEntry(BaseModel):
    date: str
    temperature_max_c: float
    temperature_min_c: float
    condition_code: int
    condition: str
    precipitation_probability_percent: float | None


class WeatherResponse(BaseModel):
    lat: float
    lng: float
    current: CurrentWeather
    daily: list[DailyForecastEntry]
