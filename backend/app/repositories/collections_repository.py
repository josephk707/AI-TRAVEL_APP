"""Repository for `favorites`/`collections`/`collection_items` — F13
Collections & Favourites (DATABASE_SCHEMA.md §6)."""

from __future__ import annotations

import uuid
from typing import Any

from app.repositories.base import Repository


class CollectionsRepository(Repository):
    # ---- favorites ----

    async def add_favorite(self, user_id: str, poi_id: str) -> None:
        await self.fetchval(
            """
            insert into public.favorites (user_id, poi_id) values ($1, $2)
            on conflict (user_id, poi_id) do nothing
            returning user_id;
            """,
            uuid.UUID(user_id),
            uuid.UUID(poi_id),
        )

    async def remove_favorite(self, user_id: str, poi_id: str) -> None:
        await self.fetchval(
            "delete from public.favorites where user_id = $1 and poi_id = $2 returning user_id;",
            uuid.UUID(user_id),
            uuid.UUID(poi_id),
        )

    async def list_favorites(self, user_id: str) -> list[dict[str, Any]]:
        rows = await self.fetch(
            """
            select f.poi_id, f.created_at, p.name as poi_name, p.category as poi_category
            from public.favorites f
            join public.pois p on p.id = f.poi_id
            where f.user_id = $1
            order by f.created_at desc;
            """,
            uuid.UUID(user_id),
        )
        return [dict(row) for row in rows]

    async def is_favorite(self, user_id: str, poi_id: str) -> bool:
        value = await self.fetchval(
            "select exists (select 1 from public.favorites where user_id = $1 and poi_id = $2);",
            uuid.UUID(user_id),
            uuid.UUID(poi_id),
        )
        return bool(value)

    # ---- collections ----

    async def create_collection(self, user_id: str, name: str) -> dict[str, Any]:
        row = await self.fetchrow(
            """
            insert into public.collections (user_id, name) values ($1, $2)
            returning id, user_id, name, created_at;
            """,
            uuid.UUID(user_id),
            name,
        )
        assert row is not None
        return dict(row)

    async def list_collections(self, user_id: str) -> list[dict[str, Any]]:
        rows = await self.fetch(
            """
            select c.id, c.user_id, c.name, c.created_at,
                   count(ci.poi_id) as item_count
            from public.collections c
            left join public.collection_items ci on ci.collection_id = c.id
            where c.user_id = $1
            group by c.id
            order by c.created_at desc;
            """,
            uuid.UUID(user_id),
        )
        return [dict(row) for row in rows]

    async def get_collection(self, collection_id: str, user_id: str) -> dict[str, Any] | None:
        row = await self.fetchrow(
            "select id, user_id, name, created_at from public.collections "
            "where id = $1 and user_id = $2;",
            uuid.UUID(collection_id),
            uuid.UUID(user_id),
        )
        return dict(row) if row else None

    async def add_item(self, collection_id: str, poi_id: str) -> None:
        await self.fetchval(
            """
            insert into public.collection_items (collection_id, poi_id) values ($1, $2)
            on conflict (collection_id, poi_id) do nothing
            returning collection_id;
            """,
            uuid.UUID(collection_id),
            uuid.UUID(poi_id),
        )

    async def list_items(self, collection_id: str) -> list[dict[str, Any]]:
        rows = await self.fetch(
            """
            select ci.poi_id, ci.added_at, p.name as poi_name, p.category as poi_category
            from public.collection_items ci
            join public.pois p on p.id = ci.poi_id
            where ci.collection_id = $1
            order by ci.added_at desc;
            """,
            uuid.UUID(collection_id),
        )
        return [dict(row) for row in rows]
