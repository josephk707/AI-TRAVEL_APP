"""Repository for `trip_invites`, `trip_members`, `trip_preferences` — F19
Group/Collaborative Trip Planning (DATABASE_SCHEMA.md §4,
migration 20260828120001)."""

from __future__ import annotations

import uuid
from typing import Any

from app.repositories.base import Repository

_INVITE_COLUMNS = (
    "id, trip_id, invited_by, method, email, token, status, created_at, "
    "expires_at, accepted_by, accepted_at"
)

_MEMBER_COLUMNS = "trip_id, user_id, role, invite_status, invited_at, responded_at"


class GroupRepository(Repository):
    # ---- invites ----

    async def create_invite(
        self, trip_id: str, invited_by: str, method: str, email: str | None
    ) -> dict[str, Any]:
        row = await self.fetchrow(
            f"""
            insert into public.trip_invites (trip_id, invited_by, method, email)
            values ($1, $2, $3, $4)
            returning {_INVITE_COLUMNS};
            """,
            uuid.UUID(trip_id),
            uuid.UUID(invited_by),
            method,
            email,
        )
        assert row is not None
        return dict(row)

    async def get_invite_by_token(self, token: str) -> dict[str, Any] | None:
        row = await self.fetchrow(
            f"select {_INVITE_COLUMNS} from public.trip_invites where token = $1;", token
        )
        return dict(row) if row else None

    async def mark_invite_accepted(self, invite_id: str, accepted_by: str) -> None:
        await self.fetchval(
            """
            update public.trip_invites
            set status = 'accepted', accepted_by = $2, accepted_at = now()
            where id = $1
            returning id;
            """,
            uuid.UUID(invite_id),
            uuid.UUID(accepted_by),
        )

    # ---- members ----

    async def add_member(self, trip_id: str, user_id: str, role: str = "member") -> dict[str, Any]:
        row = await self.fetchrow(
            f"""
            insert into public.trip_members (trip_id, user_id, role, invite_status, responded_at)
            values ($1, $2, $3, 'accepted', now())
            on conflict (trip_id, user_id) do update
                set invite_status = 'accepted', responded_at = now()
            returning {_MEMBER_COLUMNS};
            """,
            uuid.UUID(trip_id),
            uuid.UUID(user_id),
            role,
        )
        assert row is not None
        return dict(row)

    async def is_member(self, trip_id: str, user_id: str) -> bool:
        value = await self.fetchval(
            "select exists (select 1 from public.trip_members "
            "where trip_id = $1 and user_id = $2);",
            uuid.UUID(trip_id),
            uuid.UUID(user_id),
        )
        return bool(value)

    async def list_members(self, trip_id: str) -> list[dict[str, Any]]:
        rows = await self.fetch(
            """
            select m.trip_id, m.user_id, m.role, m.invite_status, m.invited_at,
                   m.responded_at, p.display_name
            from public.trip_members m
            join public.profiles p on p.id = m.user_id
            where m.trip_id = $1
            order by m.invited_at asc;
            """,
            uuid.UUID(trip_id),
        )
        return [dict(row) for row in rows]

    # ---- preferences ----

    async def upsert_preferences(
        self,
        trip_id: str,
        user_id: str,
        interests: list[str],
        budget_max: float | None,
        constraints: dict[str, Any],
    ) -> dict[str, Any]:
        # `interests`/`constraints` are passed as real Python list/dict, not
        # pre-serialized strings — the pooled connection's jsonb<->Python
        # codec (app/db/session.py) already handles encoding; json.dumps()
        # here first would double-encode (see PHASE_STATUS.md Phase 7's
        # "jsonb double-encoding bug" finding).
        row = await self.fetchrow(
            """
            insert into public.trip_preferences
                (trip_id, user_id, interests, budget_max, constraints)
            values ($1, $2, $3::jsonb, $4, $5::jsonb)
            on conflict (trip_id, user_id) do update set
                interests = excluded.interests,
                budget_max = excluded.budget_max,
                constraints = excluded.constraints,
                submitted_at = now()
            returning trip_id, user_id, interests, budget_max, constraints, submitted_at;
            """,
            uuid.UUID(trip_id),
            uuid.UUID(user_id),
            interests,
            budget_max,
            constraints,
        )
        assert row is not None
        return dict(row)

    async def list_preferences(self, trip_id: str) -> list[dict[str, Any]]:
        rows = await self.fetch(
            "select trip_id, user_id, interests, budget_max, constraints, submitted_at "
            "from public.trip_preferences where trip_id = $1;",
            uuid.UUID(trip_id),
        )
        return [dict(row) for row in rows]
