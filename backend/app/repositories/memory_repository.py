"""Repository for `memory_items` — F11 Trip Memory Box
(DATABASE_SCHEMA.md §6)."""

from __future__ import annotations

import uuid
from typing import Any

from app.repositories.base import Repository

_COLUMNS = (
    "id, trip_id, user_id, item_type, storage_path, caption, taken_at, "
    "uploaded_at, retention_expires_at, expiry_reminder_sent_at, downloaded_at, deleted_at"
)


class MemoryRepository(Repository):
    async def create(
        self,
        trip_id: str,
        user_id: str,
        item_type: str,
        storage_path: str | None,
        caption: str | None,
        taken_at: str | None,
    ) -> dict[str, Any]:
        row = await self.fetchrow(
            f"""
            insert into public.memory_items
                (trip_id, user_id, item_type, storage_path, caption, taken_at)
            values ($1, $2, $3, $4, $5, $6)
            returning {_COLUMNS};
            """,
            uuid.UUID(trip_id),
            uuid.UUID(user_id),
            item_type,
            storage_path,
            caption,
            taken_at,
        )
        assert row is not None
        return dict(row)

    async def list_for_trip(
        self, trip_id: str, limit: int = 30, offset: int = 0
    ) -> list[dict[str, Any]]:
        rows = await self.fetch(
            f"select {_COLUMNS} from public.memory_items "
            "where trip_id = $1 and deleted_at is null "
            "order by uploaded_at desc limit $2 offset $3;",
            uuid.UUID(trip_id),
            limit,
            offset,
        )
        return [dict(row) for row in rows]

    async def get(self, item_id: str, trip_id: str) -> dict[str, Any] | None:
        row = await self.fetchrow(
            f"select {_COLUMNS} from public.memory_items "
            "where id = $1 and trip_id = $2 and deleted_at is null;",
            uuid.UUID(item_id),
            uuid.UUID(trip_id),
        )
        return dict(row) if row else None

    async def soft_delete(self, item_id: str, trip_id: str, user_id: str) -> bool:
        """Explicit user deletion only — this method is never called by any
        scheduled/automated job (§43.3's hard rule)."""
        value = await self.fetchval(
            """
            update public.memory_items set deleted_at = now()
            where id = $1 and trip_id = $2
              and (user_id = $3 or exists (
                    select 1 from public.trips t where t.id = $2 and t.owner_id = $3))
            returning id;
            """,
            uuid.UUID(item_id),
            uuid.UUID(trip_id),
            uuid.UUID(user_id),
        )
        return value is not None

    async def mark_downloaded(self, item_id: str) -> None:
        await self.fetchval(
            "update public.memory_items set downloaded_at = now() where id = $1 returning id;",
            uuid.UUID(item_id),
        )
