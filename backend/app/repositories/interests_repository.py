"""
Real repository proving the Router -> Service -> Repository -> Database
pattern works against the actual schema (supabase/migrations/).

Deliberately the simplest possible non-trivial query: `interests` is a
read-only, non-user-owned lookup table (seeded reference data, not
application/business data), so this repository proves connectivity + query
execution + resource release without touching anything auth- or
ownership-related — those come with real feature endpoints in later
phases.
"""

from __future__ import annotations

from app.repositories.base import Repository


class InterestsRepository(Repository):
    async def list_interests(self) -> list[dict[str, object]]:
        rows = await self.fetch("select id, slug, label from public.interests order by id;")
        return [dict(row) for row in rows]

    async def count_interests(self) -> int:
        value = await self.fetchval("select count(*) from public.interests;")
        return int(value)
