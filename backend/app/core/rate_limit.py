"""
Per-user rate limiting for AI endpoints (API_SPECIFICATION.md §1: "AI
endpoints are limited more strictly than CRUD endpoints... 10 req/min
AI-generation endpoints, Proposed Target").

ARCHITECTURE DECISION, documented per CLAUDE.md §13 (ARCHITECTURE_REVIEW.md
H3): the PRD's Recommended stack names Redis for this; H3 flagged that
Redis was never actually added to `DEPLOYMENT_PLAN.md`, and recommended
either adding it or explicitly adopting the PRD's own stated Alternative —
"in-memory cache within the API layer for the earliest MVP" — WITH an
explicit single-instance constraint recorded. This phase adopts that
Alternative: an in-process token bucket, correct only as long as the
backend runs as a single instance (true today per `DEPLOYMENT_PLAN.md`'s
current MVP deployment target). This must be replaced with a Redis-backed
store before the backend is ever scaled to more than one instance — tracked
here and in docs/PHASE_STATUS.md, not silently left as a scaling trap.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Depends, status

from app.api.deps import get_current_user
from app.core.exceptions import AppError
from app.core.security import AuthenticatedUser

_WINDOW_SECONDS = 60.0
_AI_LIMIT_PER_WINDOW = 10

_buckets: dict[str, deque[float]] = defaultdict(deque)


def _check(user_id: str, limit: int, window: float) -> bool:
    now = time.monotonic()
    bucket = _buckets[user_id]
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


async def ai_rate_limit(user: AuthenticatedUser = Depends(get_current_user)) -> None:
    if not _check(f"ai:{user.id}", _AI_LIMIT_PER_WINDOW, _WINDOW_SECONDS):
        raise AppError(
            "RATE_LIMITED",
            "Too many AI requests — please wait a moment before trying again.",
            status.HTTP_429_TOO_MANY_REQUESTS,
        )


def reset_rate_limits_for_tests() -> None:
    _buckets.clear()
