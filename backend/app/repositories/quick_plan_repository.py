"""Repository for `quick_plans`/`quick_plan_items` — F22 Weekend/Local
Outing Quick Plan (DATABASE_SCHEMA.md §11, migration 20260825120009)."""

from __future__ import annotations

import uuid
from typing import Any

from app.repositories.base import Repository


class QuickPlanRepository(Repository):
    async def create_plan(
        self,
        user_id: str,
        time_available_min: int | None,
        budget: float | None,
        occasion: str | None,
    ) -> dict[str, Any]:
        row = await self.fetchrow(
            """
            insert into public.quick_plans (user_id, time_available_min, budget, occasion)
            values ($1, $2, $3, $4)
            returning id, user_id, time_available_min, budget, occasion, generated_at;
            """,
            uuid.UUID(user_id),
            time_available_min,
            budget,
            occasion,
        )
        assert row is not None
        return dict(row)

    async def add_items(self, quick_plan_id: str, items: list[dict[str, Any]]) -> None:
        for item in items:
            await self.fetchval(
                """
                insert into public.quick_plan_items (quick_plan_id, poi_id, sequence_order)
                values ($1, $2, $3)
                returning quick_plan_id;
                """,
                uuid.UUID(quick_plan_id),
                uuid.UUID(item["poi_id"]),
                item["sequence_order"],
            )

    async def get_plan(self, quick_plan_id: str, user_id: str) -> dict[str, Any] | None:
        row = await self.fetchrow(
            "select id, user_id, time_available_min, budget, occasion, generated_at "
            "from public.quick_plans where id = $1 and user_id = $2;",
            uuid.UUID(quick_plan_id),
            uuid.UUID(user_id),
        )
        return dict(row) if row else None

    async def list_items(self, quick_plan_id: str) -> list[dict[str, Any]]:
        rows = await self.fetch(
            """
            select qi.poi_id, qi.sequence_order, p.name as poi_name, p.category as poi_category
            from public.quick_plan_items qi
            join public.pois p on p.id = qi.poi_id
            where qi.quick_plan_id = $1
            order by qi.sequence_order asc;
            """,
            uuid.UUID(quick_plan_id),
        )
        return [dict(row) for row in rows]
