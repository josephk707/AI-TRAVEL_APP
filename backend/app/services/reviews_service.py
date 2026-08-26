"""
F14 — Reviews & Ratings (IMPLEMENTATION_BLUEPRINT.md F14, API_SPECIFICATION.md
§12/§19). Eligibility ("must have a completed trip that included this
place") is checked here in the application layer AND enforced again by the
database's own `reviews_insert_own` RLS predicate — defense in depth
(CLAUDE.md §5), not a substitute for each other.
"""

from __future__ import annotations

from app.core.exceptions import AppError, NotFoundError
from app.repositories.ai_conversations_repository import FeedbackRepository
from app.repositories.pois_repository import PoisRepository
from app.repositories.reviews_repository import ReviewsRepository
from app.services import analytics_service


async def create_review(
    user_id: str, poi_id: str, trip_id: str, rating: int, review_text: str | None
) -> dict:
    poi = await PoisRepository().get_by_id(poi_id)
    if poi is None:
        raise NotFoundError("This place could not be found.")

    repo = ReviewsRepository()
    if not await repo.is_eligible(user_id, poi_id, trip_id):
        raise AppError(
            "REVIEW_NOT_ELIGIBLE",
            "You can only review places from a trip you've completed.",
            403,
        )

    review = await repo.create_review(user_id, poi_id, trip_id, rating, review_text)
    # Published review sentiment factors into future recommendation ranking
    # (AI_ARCHITECTURE.md §7 table) — logged as a real personalization
    # signal now, not deferred until moderation (the SIGNAL is the
    # traveller's own rating, independent of whether it's later published).
    await FeedbackRepository().log_signal(
        user_id,
        trip_id=trip_id,
        itinerary_item_id=None,
        signal_type="review_submitted",
        value={"poi_id": poi_id, "rating": rating},
    )
    await analytics_service.track(user_id, "review_submitted", {"poi_id": poi_id, "rating": rating})
    return review


async def list_reviews_for_poi(poi_id: str, limit: int = 20, offset: int = 0) -> list[dict]:
    return await ReviewsRepository().list_published_for_poi(poi_id, limit, offset)


async def list_pending_reviews() -> list[dict]:
    return await ReviewsRepository().list_pending()


async def moderate_review(review_id: str, moderator_id: str, decision: str) -> dict:
    review = await ReviewsRepository().moderate(review_id, moderator_id, decision)
    if review is None:
        raise NotFoundError("This review could not be found.")
    return review
