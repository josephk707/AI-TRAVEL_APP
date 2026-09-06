"""
Repository for `personalization_profile` and the aggregate reads over
`feedback_signals` the Personalization Engine needs (both tables already
existed, unused, since migration 20260825120008 — Final Personalization
phase reuses them as designed, no new table).

Trust boundary: every method takes a `user_id` that MUST already be a
cryptographically verified identity — same discipline as every other
repository in this codebase (see ProfilesRepository's docstring).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from app.repositories.base import Repository


class PersonalizationRepository(Repository):
    async def get_profile(self, user_id: str) -> dict[str, Any] | None:
        row = await self.fetchrow(
            "select user_id, preference_weights, updated_at "
            "from public.personalization_profile where user_id = $1;",
            uuid.UUID(user_id),
        )
        return dict(row) if row else None

    async def upsert_profile(
        self, user_id: str, preference_weights: dict[str, Any]
    ) -> dict[str, Any]:
        """Server-side only write (the table's own RLS deliberately has no
        client-facing INSERT/UPDATE policy — see the migration's comment);
        this backend connects via the pooled connection that bypasses RLS
        entirely, matching every other repository's write path here, so no
        RLS change was needed or made."""
        row = await self.fetchrow(
            """
            insert into public.personalization_profile (user_id, preference_weights)
            values ($1, $2::jsonb)
            on conflict (user_id) do update set
                preference_weights = excluded.preference_weights,
                updated_at = now()
            returning user_id, preference_weights, updated_at;
            """,
            uuid.UUID(user_id),
            json.dumps(preference_weights),
        )
        assert row is not None
        return dict(row)

    async def get_signal_counts(self, user_id: str) -> dict[str, int]:
        """Real behavioral signal (F17 feedback, favoriting — both already
        write real `feedback_signals` rows today) aggregated by type —
        the "travel behaviour/signals" layer of the personalization
        pipeline. Never raw event rows, just counts."""
        rows = await self.fetch(
            "select signal_type, count(*) as n from public.feedback_signals "
            "where user_id = $1 group by signal_type;",
            uuid.UUID(user_id),
        )
        return {row["signal_type"]: int(row["n"]) for row in rows}
