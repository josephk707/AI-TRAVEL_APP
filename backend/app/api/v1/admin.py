"""/v1/admin/* — F14 review moderation only (API_SPECIFICATION.md §19).

The rest of §19 (POI/heritage-content curation) is intentionally NOT
built here — that content is authored via the maintainer scripts
established in Phase 6 (`scripts/seed_heritage_content.py`), a documented
decision carried forward, not a gap. Review moderation is genuinely new
Phase 7 scope: without it, a submitted review can never become visible,
which would make F14 a non-functional half-feature.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope
from app.schemas.reviews import ModerateReviewRequest, ReviewResponse
from app.services import analytics_service, reviews_service

router = APIRouter(prefix="/admin", tags=["admin"])


def _to_response(row: dict) -> dict:
    return dict(
        row,
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        poi_id=str(row["poi_id"]),
        trip_id=str(row["trip_id"]),
    )


@router.get("/reviews/pending", response_model=Envelope[list[ReviewResponse]])
async def list_pending_reviews(
    admin: AuthenticatedUser = Depends(require_admin),
) -> Envelope[list[ReviewResponse]]:
    del admin
    rows = await reviews_service.list_pending_reviews()
    return Envelope(data=[ReviewResponse.model_validate(_to_response(r)) for r in rows])


@router.patch("/reviews/{review_id}/moderate", response_model=Envelope[ReviewResponse])
async def moderate_review(
    review_id: str,
    body: ModerateReviewRequest,
    admin: AuthenticatedUser = Depends(require_admin),
) -> Envelope[ReviewResponse]:
    review = await reviews_service.moderate_review(review_id, admin.id, body.decision)
    return Envelope(data=ReviewResponse.model_validate(_to_response(review)))


@router.get("/analytics/kpis", response_model=Envelope[dict])
async def get_kpis(admin: AuthenticatedUser = Depends(require_admin)) -> Envelope[dict]:
    del admin
    kpis = await analytics_service.get_kpis()
    return Envelope(data=kpis)
