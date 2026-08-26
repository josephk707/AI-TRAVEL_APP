"""Repository for `notifications`/`device_push_tokens` — F16
(DATABASE_SCHEMA.md §7)."""

from __future__ import annotations

import uuid
from typing import Any

from app.repositories.base import Repository

_NOTIFICATION_COLUMNS = (
    "id, user_id, trip_id, type, title, body, payload, read_at, delivered_channels, created_at"
)


class NotificationsRepository(Repository):
    async def create(
        self,
        user_id: str,
        *,
        trip_id: str | None,
        type_: str,
        title: str,
        body: str,
        payload: dict[str, Any] | None = None,
        delivered_channels: list[str] | None = None,
    ) -> dict[str, Any]:
        row = await self.fetchrow(
            f"""
            insert into public.notifications
                (user_id, trip_id, type, title, body, payload, delivered_channels)
            values ($1, $2, $3, $4, $5, $6::jsonb, $7)
            returning {_NOTIFICATION_COLUMNS};
            """,
            uuid.UUID(user_id),
            uuid.UUID(trip_id) if trip_id else None,
            type_,
            title,
            body,
            # A real Python dict, not a pre-serialized string — the pooled
            # connection's jsonb<->dict codec (app/db/session.py) already
            # handles encoding; json.dumps()-ing it here first would
            # double-encode and round-trip back as a str, not a dict.
            payload or {},
            delivered_channels or [],
        )
        assert row is not None
        return dict(row)

    async def list_for_user(
        self, user_id: str, limit: int = 30, offset: int = 0
    ) -> list[dict[str, Any]]:
        rows = await self.fetch(
            f"select {_NOTIFICATION_COLUMNS} from public.notifications "
            "where user_id = $1 order by created_at desc limit $2 offset $3;",
            uuid.UUID(user_id),
            limit,
            offset,
        )
        return [dict(row) for row in rows]

    async def mark_read(self, notification_id: str, user_id: str) -> dict[str, Any] | None:
        row = await self.fetchrow(
            f"""
            update public.notifications set read_at = now()
            where id = $1 and user_id = $2
            returning {_NOTIFICATION_COLUMNS};
            """,
            uuid.UUID(notification_id),
            uuid.UUID(user_id),
        )
        return dict(row) if row else None


class PushTokenRepository(Repository):
    async def upsert(self, user_id: str, expo_push_token: str, platform: str) -> None:
        await self.fetchval(
            """
            insert into public.device_push_tokens (user_id, expo_push_token, platform)
            values ($1, $2, $3)
            on conflict (expo_push_token)
                do update set user_id = excluded.user_id, platform = excluded.platform
            returning id;
            """,
            uuid.UUID(user_id),
            expo_push_token,
            platform,
        )

    async def delete(self, user_id: str, expo_push_token: str) -> None:
        await self.fetchval(
            "delete from public.device_push_tokens "
            "where user_id = $1 and expo_push_token = $2 returning id;",
            uuid.UUID(user_id),
            expo_push_token,
        )

    async def list_tokens_for_user(self, user_id: str) -> list[str]:
        rows = await self.fetch(
            "select expo_push_token from public.device_push_tokens where user_id = $1;",
            uuid.UUID(user_id),
        )
        return [row["expo_push_token"] for row in rows]
