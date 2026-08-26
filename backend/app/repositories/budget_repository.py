"""Repository for `budget_expenses` — F15 Budget Estimate
(DATABASE_SCHEMA.md §8)."""

from __future__ import annotations

import uuid
from typing import Any

from app.repositories.base import Repository


class BudgetRepository(Repository):
    async def create_expense(
        self, trip_id: str, user_id: str, category: str, amount: float, currency: str
    ) -> dict[str, Any]:
        row = await self.fetchrow(
            """
            insert into public.budget_expenses (trip_id, user_id, category, amount, currency)
            values ($1, $2, $3, $4, $5)
            returning id, trip_id, user_id, category, amount, currency, logged_at;
            """,
            uuid.UUID(trip_id),
            uuid.UUID(user_id),
            category,
            amount,
            currency,
        )
        assert row is not None
        return dict(row)

    async def list_expenses(self, trip_id: str) -> list[dict[str, Any]]:
        rows = await self.fetch(
            "select id, trip_id, user_id, category, amount, currency, logged_at "
            "from public.budget_expenses where trip_id = $1 order by logged_at desc;",
            uuid.UUID(trip_id),
        )
        return [dict(row) for row in rows]

    async def total_spent(self, trip_id: str) -> float:
        value = await self.fetchval(
            "select coalesce(sum(amount), 0) from public.budget_expenses where trip_id = $1;",
            uuid.UUID(trip_id),
        )
        return float(value)
