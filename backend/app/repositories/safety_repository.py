"""Repository for `trusted_contacts`, `trip_location_shares`, `sos_events`
— F21 Safety/SOS (DATABASE_SCHEMA.md §9, migration 20260825120007)."""

from __future__ import annotations

import uuid
from typing import Any

from app.repositories.base import Repository

_CONTACT_COLUMNS = "id, user_id, name, phone, email, created_at"
_SHARE_COLUMNS = "id, trip_id, user_id, share_token, is_active, started_at, expires_at"
_SOS_COLUMNS = (
    "id, user_id, trip_id, triggered_at, last_known_lat, last_known_lng, "
    "location_captured_at, resolved_at"
)


class SafetyRepository(Repository):
    # ---- trusted contacts ----

    async def add_contact(
        self, user_id: str, name: str, phone: str | None, email: str | None
    ) -> dict[str, Any]:
        row = await self.fetchrow(
            f"""
            insert into public.trusted_contacts (user_id, name, phone, email)
            values ($1, $2, $3, $4)
            returning {_CONTACT_COLUMNS};
            """,
            uuid.UUID(user_id),
            name,
            phone,
            email,
        )
        assert row is not None
        return dict(row)

    async def list_contacts(self, user_id: str) -> list[dict[str, Any]]:
        rows = await self.fetch(
            f"select {_CONTACT_COLUMNS} from public.trusted_contacts "
            "where user_id = $1 order by created_at asc;",
            uuid.UUID(user_id),
        )
        return [dict(row) for row in rows]

    # ---- location shares ----

    async def start_share(self, trip_id: str, user_id: str, expires_at: Any) -> dict[str, Any]:
        row = await self.fetchrow(
            f"""
            insert into public.trip_location_shares (trip_id, user_id, expires_at)
            values ($1, $2, $3)
            returning {_SHARE_COLUMNS};
            """,
            uuid.UUID(trip_id),
            uuid.UUID(user_id),
            expires_at,
        )
        assert row is not None
        return dict(row)

    async def stop_share(self, trip_id: str, user_id: str) -> None:
        await self.fetchval(
            """
            update public.trip_location_shares
            set is_active = false
            where trip_id = $1 and user_id = $2 and is_active = true
            returning id;
            """,
            uuid.UUID(trip_id),
            uuid.UUID(user_id),
        )

    async def get_active_share_by_token(self, share_token: str) -> dict[str, Any] | None:
        row = await self.fetchrow(
            f"""
            select {_SHARE_COLUMNS} from public.trip_location_shares
            where share_token = $1 and is_active = true and expires_at > now();
            """,
            share_token,
        )
        return dict(row) if row else None

    async def get_latest_location(self, trip_id: str, user_id: str) -> dict[str, Any] | None:
        row = await self.fetchrow(
            """
            select ST_Y(location::geometry) as lat, ST_X(location::geometry) as lng, recorded_at
            from public.location_pings
            where trip_id = $1 and user_id = $2
            order by recorded_at desc
            limit 1;
            """,
            uuid.UUID(trip_id),
            uuid.UUID(user_id),
        )
        return dict(row) if row else None

    # ---- SOS ----

    async def create_sos_event(
        self,
        user_id: str,
        trip_id: str | None,
        last_known_lat: float | None,
        last_known_lng: float | None,
        location_captured_at: Any,
    ) -> dict[str, Any]:
        row = await self.fetchrow(
            f"""
            insert into public.sos_events
                (user_id, trip_id, last_known_lat, last_known_lng, location_captured_at)
            values ($1, $2, $3, $4, $5)
            returning {_SOS_COLUMNS};
            """,
            uuid.UUID(user_id),
            uuid.UUID(trip_id) if trip_id else None,
            last_known_lat,
            last_known_lng,
            location_captured_at,
        )
        assert row is not None
        return dict(row)
