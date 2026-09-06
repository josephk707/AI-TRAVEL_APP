"""/v1/personalization/* — Final Personalization phase. Real user-specific
Travel DNA, computed from the caller's own verified identity only (never
a client-supplied user id) — see app/services/personalization_service.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope
from app.schemas.personalization import TravelDnaResponse
from app.services import personalization_service

router = APIRouter(prefix="/personalization", tags=["personalization"])


@router.get("/travel-dna", response_model=Envelope[TravelDnaResponse])
async def get_travel_dna(
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[TravelDnaResponse]:
    result = await personalization_service.compute_travel_dna(user.id)
    return Envelope(data=TravelDnaResponse.model_validate(result))
