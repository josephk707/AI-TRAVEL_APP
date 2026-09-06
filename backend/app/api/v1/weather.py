"""/v1/weather — Maps Integration phase, real Open-Meteo destination
weather. See app/services/open_meteo_client.py's module docstring for
why this is separate from the pre-existing internal weather pipeline."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope
from app.schemas.weather import WeatherQuery, WeatherResponse
from app.services import open_meteo_service

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("", response_model=Envelope[WeatherResponse])
async def get_weather(
    params: WeatherQuery = Depends(),
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[WeatherResponse]:
    del user
    result = await open_meteo_service.get_weather(params.lat, params.lng)
    return Envelope(data=WeatherResponse.model_validate(result))
