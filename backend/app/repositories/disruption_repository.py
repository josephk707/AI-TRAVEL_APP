"""Repository for `disruption_events` — F20 Dynamic Itinerary Re-Adaptation
(DATABASE_SCHEMA.md §11, migration 20260825120009)."""

from __future__ import annotations

import uuid
from typing import Any

from app.repositories.base import Repository

_COLUMNS = (
    "id, trip_id, itinerary_item_id, trigger_type, detected_at, proposal, " "status, resolved_at"
)


class DisruptionRepository(Repository):
    async def create(
        self, trip_id: str, itinerary_item_id: str, trigger_type: str, proposal: dict[str, Any]
    ) -> dict[str, Any]:
        # `proposal` is a real Python dict — the pooled connection's
        # jsonb<->dict codec handles encoding; do not json.dumps() it first
        # (see PHASE_STATUS.md Phase 7's "jsonb double-encoding bug" finding).
        row = await self.fetchrow(
            f"""
            insert into public.disruption_events
                (trip_id, itinerary_item_id, trigger_type, proposal)
            values ($1, $2, $3, $4::jsonb)
            returning {_COLUMNS};
            """,
            uuid.UUID(trip_id),
            uuid.UUID(itinerary_item_id),
            trigger_type,
            proposal,
        )
        assert row is not None
        return dict(row)

    async def has_open_proposal_for_item(self, itinerary_item_id: str) -> bool:
        value = await self.fetchval(
            "select exists (select 1 from public.disruption_events "
            "where itinerary_item_id = $1 and status = 'proposed');",
            uuid.UUID(itinerary_item_id),
        )
        return bool(value)

    async def list_for_trip(self, trip_id: str) -> list[dict[str, Any]]:
        rows = await self.fetch(
            f"select {_COLUMNS} from public.disruption_events "
            "where trip_id = $1 order by detected_at desc;",
            uuid.UUID(trip_id),
        )
        return [dict(row) for row in rows]

    async def get(self, event_id: str, trip_id: str) -> dict[str, Any] | None:
        row = await self.fetchrow(
            f"select {_COLUMNS} from public.disruption_events where id = $1 and trip_id = $2;",
            uuid.UUID(event_id),
            uuid.UUID(trip_id),
        )
        return dict(row) if row else None

    async def resolve(self, event_id: str, trip_id: str, status: str) -> dict[str, Any] | None:
        row = await self.fetchrow(
            f"""
            update public.disruption_events
            set status = $3, resolved_at = now()
            where id = $1 and trip_id = $2
            returning {_COLUMNS};
            """,
            uuid.UUID(event_id),
            uuid.UUID(trip_id),
            status,
        )
        return dict(row) if row else None
