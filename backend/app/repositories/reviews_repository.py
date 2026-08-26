"""Repository for `reviews` — F14 Reviews & Ratings (DATABASE_SCHEMA.md §6)."""

from __future__ import annotations

import uuid
from typing import Any

from app.repositories.base import Repository

_REVIEW_COLUMNS = (
    "id, user_id, poi_id, trip_id, rating, review_text, status, "
    "moderated_by, moderated_at, created_at"
)


class ReviewsRepository(Repository):
    async def is_eligible(self, user_id: str, poi_id: str, trip_id: str) -> bool:
        """Mirrors the DB's own `reviews_insert_own` RLS check exactly —
        checked again in the application layer so the error is a clean,
        specific 403 REVIEW_NOT_ELIGIBLE rather than a raw RLS denial."""
        value = await self.fetchval(
            """
            select exists (
                select 1 from public.trips t
                where t.id = $1 and t.owner_id = $2 and t.status = 'completed'
            );
            """,
            uuid.UUID(trip_id),
            uuid.UUID(user_id),
        )
        return bool(value)

    async def create_review(
        self, user_id: str, poi_id: str, trip_id: str, rating: int, review_text: str | None
    ) -> dict[str, Any]:
        row = await self.fetchrow(
            f"""
            insert into public.reviews (user_id, poi_id, trip_id, rating, review_text)
            values ($1, $2, $3, $4, $5)
            returning {_REVIEW_COLUMNS};
            """,
            uuid.UUID(user_id),
            uuid.UUID(poi_id),
            uuid.UUID(trip_id),
            rating,
            review_text,
        )
        assert row is not None
        return dict(row)

    async def list_pending(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self.fetch(
            f"select {_REVIEW_COLUMNS} from public.reviews "
            "where status = 'pending' order by created_at asc limit $1;",
            limit,
        )
        return [dict(row) for row in rows]

    async def moderate(
        self, review_id: str, moderator_id: str, decision: str
    ) -> dict[str, Any] | None:
        new_status = "published" if decision == "publish" else "rejected"
        row = await self.fetchrow(
            f"""
            update public.reviews
            set status = $2, moderated_by = $3, moderated_at = now()
            where id = $1
            returning {_REVIEW_COLUMNS};
            """,
            uuid.UUID(review_id),
            new_status,
            uuid.UUID(moderator_id),
        )
        return dict(row) if row else None

    async def list_published_for_poi(
        self, poi_id: str, limit: int = 20, offset: int = 0
    ) -> list[dict[str, Any]]:
        rows = await self.fetch(
            f"""
            select {_REVIEW_COLUMNS} from public.reviews
            where poi_id = $1 and status = 'published'
            order by created_at desc
            limit $2 offset $3;
            """,
            uuid.UUID(poi_id),
            limit,
            offset,
        )
        return [dict(row) for row in rows]
