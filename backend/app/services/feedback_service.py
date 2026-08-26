"""
F17 — Post-Trip Feedback Capture (IMPLEMENTATION_BLUEPRINT.md F17,
AI_ARCHITECTURE.md §7.2, API_SPECIFICATION.md §17). The highest-quality
personalization signal (§10.3, §20) — each per-stop thumbs up/down is
logged as its own real `feedback_signals` row, immediately available to
the Personalization Engine's batched recompute (AI_ARCHITECTURE.md §7.1);
skipping feedback never blocks anything (FR-018 alt. flow — this endpoint
is purely additive, there is no "must submit" gate anywhere in the trip
lifecycle).
"""

from __future__ import annotations

from app.core.exceptions import ForbiddenError, NotFoundError
from app.repositories.ai_conversations_repository import FeedbackRepository
from app.repositories.trips_repository import TripsRepository
from app.schemas.feedback import TripFeedbackRequest
from app.services import analytics_service


async def submit_feedback(trip_id: str, user_id: str, body: TripFeedbackRequest) -> dict:
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")

    feedback_repo = FeedbackRepository()
    signals_recorded = 0

    for stop in body.stops:
        await feedback_repo.log_signal(
            user_id,
            trip_id=trip_id,
            itinerary_item_id=stop.itinerary_item_id,
            signal_type=stop.signal,
            value={},
        )
        signals_recorded += 1

    if body.free_text:
        # The `feedback_signals.signal_type` check constraint has no
        # dedicated "free text" value — documented decision (CLAUDE.md
        # §13): carried as the `value` payload of an 'accept' signal (a
        # neutral container), the free text itself, not the signal type,
        # is what the Personalization Engine / human review reads.
        await feedback_repo.log_signal(
            user_id,
            trip_id=trip_id,
            itinerary_item_id=None,
            signal_type="accept",
            value={"free_text": body.free_text},
        )
        signals_recorded += 1

    await analytics_service.track(
        user_id, "feedback_submitted", {"trip_id": trip_id, "signals_recorded": signals_recorded}
    )
    return {"trip_id": trip_id, "signals_recorded": signals_recorded}
