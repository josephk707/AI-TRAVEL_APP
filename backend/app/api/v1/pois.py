"""
/v1/pois/* — see docs/API_SPECIFICATION.md §5 for the full contract.

Every route requires a real, cryptographically verified Supabase access
token (via app.api.deps.get_current_user) — POIs are shared reference data
(not user-owned), so the caller identity isn't used for scoping, only for
the same authenticated-access requirement every other /v1 endpoint enforces
(API_SPECIFICATION.md §1).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope, Meta
from app.schemas.poi import PoiNearbyQuery, PoiResponse, PoiSearchQuery
from app.services import poi_service

router = APIRouter(prefix="/pois", tags=["pois"])


@router.get("/search", response_model=Envelope[list[PoiResponse]])
async def search_pois(
    params: PoiSearchQuery = Depends(),
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[list[PoiResponse]]:
    """Text/category/bounding-box search — backend-cached proxy over Google
    Places (§5). Degrades to cache-only results (never a hard failure) when
    live search is unavailable — `meta.degraded_mode` tells the client.

    `params` is taken as a `Depends()`-injected pydantic model (not
    individual `Query(...)` parameters) specifically so its cross-field
    `_require_query_or_location` validator runs through FastAPI's own
    request-validation pipeline — and therefore this project's standard
    400 VALIDATION_ERROR envelope (app/core/exceptions.py) — rather than
    raising a raw, unhandled pydantic ValidationError if constructed
    manually inside the handler body (a real bug caught by this phase's
    own live tests, not a hypothetical one)."""
    del user
    results, degraded = await poi_service.search(params)
    meta = (
        Meta(
            degraded_mode=True,
            message="Live search is temporarily unavailable — showing curated results only.",
        )
        if degraded
        else None
    )
    return Envelope(data=[PoiResponse.model_validate(row) for row in results], meta=meta)


@router.get("/nearby", response_model=Envelope[list[PoiResponse]])
async def nearby_pois(
    params: PoiNearbyQuery = Depends(),
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[list[PoiResponse]]:
    """`ST_DWithin` query against the real database — no live provider call
    (see app/services/poi_service.py's module docstring for why)."""
    del user
    results = await poi_service.nearby(params)
    return Envelope(data=[PoiResponse.model_validate(row) for row in results])


@router.get("/{poi_id}", response_model=Envelope[PoiResponse])
async def get_poi(
    poi_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[PoiResponse]:
    del user
    result = await poi_service.get_by_id(poi_id)
    return Envelope(data=PoiResponse.model_validate(result))
