"""/v1/trips/{id}/offline-package — F26 (see app/schemas/offline.py's
module docstring)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope
from app.schemas.offline import OfflinePackageResponse
from app.services import offline_service

router = APIRouter(tags=["offline"])


@router.get("/trips/{trip_id}/offline-package", response_model=Envelope[OfflinePackageResponse])
async def get_offline_package(
    trip_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[OfflinePackageResponse]:
    result = await offline_service.get_offline_package(trip_id, user.id)
    return Envelope(data=OfflinePackageResponse.model_validate(result))
