"""
Repository for the `profiles` table (supabase/migrations/20260825120002_*).

Trust boundary: every method takes a `user_id` that MUST already be a
cryptographically verified identity (app/core/security.py's
AuthenticatedUser.id) — never a client-supplied value. The backend
connects to Postgres via the shared service-role-equivalent pool
(app/db/session.py), which bypasses Row Level Security entirely, so this
repository's own `where id = $1` scoping IS the authorization boundary at
this layer. RLS (tested separately in tests/test_rls_security.py) is a
second, independent layer of defense-in-depth — not a substitute for
scoping correctly here.
"""

from __future__ import annotations

import uuid

from app.repositories.base import Repository

_PROFILE_COLUMNS = (
    "id, display_name, avatar_url, home_region, travel_style, pace, "
    "budget_bracket, travel_companion, trip_motivation, role, preferred_language, "
    "onboarding_completed_at, created_at, updated_at"
)


class ProfilesRepository(Repository):
    async def get_by_id(self, user_id: str) -> dict[str, object] | None:
        row = await self.fetchrow(
            f"select {_PROFILE_COLUMNS} from public.profiles where id = $1;",
            uuid.UUID(user_id),
        )
        return dict(row) if row else None

    async def create_if_missing(self, user_id: str) -> dict[str, object]:
        """Idempotently provisions a profile row for `user_id`.

        Normal operation never needs this: `handle_new_user()` (the DB
        trigger on auth.users, DATABASE_SCHEMA.md §3) already creates the
        row the moment Supabase Auth creates the user, before any API call
        can happen. This exists purely as a defensive fallback for an
        already-authenticated caller whose trigger-created row is somehow
        missing — it is not a general-purpose "create a profile for anyone"
        path, since it only ever runs after get_current_user() has verified
        a real token for that exact id.
        """
        row = await self.fetchrow(
            f"""
            insert into public.profiles (id)
            values ($1)
            on conflict (id) do update set id = excluded.id
            returning {_PROFILE_COLUMNS};
            """,
            uuid.UUID(user_id),
        )
        assert row is not None  # INSERT ... RETURNING always yields exactly one row here
        return dict(row)

    async def update_preferred_language(
        self, user_id: str, preferred_language: str
    ) -> dict[str, object]:
        """The database CHECK constraint (migration
        20260828120002_add_preferred_language.sql) is the actual source of
        truth for the allowed set — this repository does not duplicate that
        list; an invalid value raises a constraint-violation error the
        service layer maps to a 400."""
        row = await self.fetchrow(
            f"""
            update public.profiles
            set preferred_language = $2
            where id = $1
            returning {_PROFILE_COLUMNS};
            """,
            uuid.UUID(user_id),
            preferred_language,
        )
        assert row is not None  # caller (auth_service) already verified the profile exists
        return dict(row)
