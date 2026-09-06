"""
Repository for the onboarding write/read path — spans `profiles` and
`profile_interests` (supabase/migrations/20260825120002_*), since a single
onboarding submission updates both atomically.

Trust boundary: every method takes a `profile_id` that MUST already be a
cryptographically verified identity (app/core/security.py's
AuthenticatedUser.id) — never a client-supplied value. Same scoping
discipline as ProfilesRepository (see that module's docstring).
"""

from __future__ import annotations

import uuid

from app.repositories.base import Repository

_ONBOARDING_PROFILE_COLUMNS = (
    "onboarding_completed_at, travel_style, pace, budget_bracket, travel_companion, trip_motivation"
)


class OnboardingRepository(Repository):
    async def get_interest_ids_for_profile(self, profile_id: str) -> list[int]:
        rows = await self.fetch(
            "select interest_id from public.profile_interests "
            "where profile_id = $1 order by interest_id;",
            uuid.UUID(profile_id),
        )
        return [int(row["interest_id"]) for row in rows]

    async def get_onboarding_state(self, profile_id: str) -> dict[str, object] | None:
        row = await self.fetchrow(
            f"select {_ONBOARDING_PROFILE_COLUMNS} from public.profiles where id = $1;",
            uuid.UUID(profile_id),
        )
        return dict(row) if row else None

    async def save_onboarding_responses(
        self,
        profile_id: str,
        *,
        interest_ids: list[int],
        travel_style: str | None,
        pace: str | None,
        budget_bracket: str | None,
        travel_companion: str | None = None,
        trip_motivation: str | None = None,
    ) -> dict[str, object]:
        """Atomically updates `profiles` and replaces this profile's
        `source = 'onboarding'` rows in `profile_interests` with the given
        set. Rows with any OTHER source (`inferred`, `explicit_feedback` —
        written by later phases' Personalization Engine, AI_ARCHITECTURE.md
        §7) are left untouched, so re-running onboarding never discards
        signal the app has learned from actual behavior.

        Only interest ids already validated by the caller (against
        InterestsRepository's known set) should reach this method — see
        onboarding_service.py. A genuinely unknown id would still fail
        safely here via the profile_interests.interest_id foreign key, just
        with a less specific error than the service layer's own check.
        """
        pid = uuid.UUID(profile_id)
        async with self.transaction() as conn:
            await conn.execute(
                """
                update public.profiles
                set travel_style = coalesce($2, travel_style),
                    pace = coalesce($3, pace),
                    budget_bracket = coalesce($4, budget_bracket),
                    travel_companion = coalesce($5, travel_companion),
                    trip_motivation = coalesce($6, trip_motivation),
                    onboarding_completed_at = now(),
                    updated_at = now()
                where id = $1;
                """,
                pid,
                travel_style,
                pace,
                budget_bracket,
                travel_companion,
                trip_motivation,
            )
            await conn.execute(
                "delete from public.profile_interests "
                "where profile_id = $1 and source = 'onboarding';",
                pid,
            )
            if interest_ids:
                await conn.executemany(
                    """
                    insert into public.profile_interests (profile_id, interest_id, source)
                    values ($1, $2, 'onboarding')
                    on conflict (profile_id, interest_id)
                    do update set source = 'onboarding', updated_at = now();
                    """,
                    [(pid, interest_id) for interest_id in interest_ids],
                )
            row = await conn.fetchrow(
                f"select {_ONBOARDING_PROFILE_COLUMNS} from public.profiles where id = $1;",
                pid,
            )
        assert row is not None  # the profile row is guaranteed to exist (trigger-provisioned)
        return dict(row)
