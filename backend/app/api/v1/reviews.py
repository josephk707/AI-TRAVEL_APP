"""/v1/reviews, /v1/pois/{id}/reviews — F14 (API_SPECIFICATION.md §12)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.security import AuthenticatedUser
from app.schemas.common import Envelope
from app.schemas.reviews import ReviewCreateRequest, ReviewResponse
from app.services import reviews_service

router = APIRouter(tags=["reviews"])


def _to_response(row: dict) -> dict:
    return dict(
        row,
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        poi_id=str(row["poi_id"]),
        trip_id=str(row["trip_id"]),
    )


@router.post("/reviews", response_model=Envelope[ReviewResponse], status_code=201)
async def create_review(
    body: ReviewCreateRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[ReviewResponse]:
    review = await reviews_service.create_review(
        user.id, body.poi_id, body.trip_id, body.rating, body.review_text
    )
    return Envelope(data=ReviewResponse.model_validate(_to_response(review)))


@router.get("/pois/{poi_id}/reviews", response_model=Envelope[list[ReviewResponse]])
async def list_poi_reviews(
    poi_id: str,
    limit: int = 20,
    offset: int = 0,
    user: AuthenticatedUser = Depends(get_current_user),
) -> Envelope[list[ReviewResponse]]:
    del user
    rows = await reviews_service.list_reviews_for_poi(poi_id, limit, offset)
    return Envelope(data=[ReviewResponse.model_validate(_to_response(r)) for r in rows])
