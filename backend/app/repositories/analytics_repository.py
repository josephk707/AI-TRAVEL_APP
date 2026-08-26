"""Repository for `analytics_events` — F18 Analytics (Internal)
(DATABASE_SCHEMA.md §12)."""

from __future__ import annotations

import uuid
from typing import Any

from app.repositories.base import Repository


class AnalyticsRepository(Repository):
    async def record(
        self, user_id: str | None, event_name: str, properties: dict[str, Any] | None = None
    ) -> None:
        # `properties` is passed as a real Python dict, not a pre-serialized
        # string — app/db/session.py already registers a jsonb<->dict codec
        # on every pooled connection, so json.dumps()-ing it here first would
        # double-encode (the codec's own encoder would then re-serialize the
        # already-JSON string, round-tripping back as a str, not a dict).
        await self.fetchval(
            """
            insert into public.analytics_events (user_id, event_name, properties)
            values ($1, $2, $3::jsonb)
            returning id;
            """,
            uuid.UUID(user_id) if user_id else None,
            event_name,
            properties or {},
        )

    async def count_event(self, event_name: str) -> int:
        value = await self.fetchval(
            "select count(*) from public.analytics_events where event_name = $1;", event_name
        )
        return int(value)
