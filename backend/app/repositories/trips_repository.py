"""
Repository for `trips`, `itinerary_days`, `itinerary_items`, and
`trip_raw_notes` — F3/F4/F5/F12 (supabase/migrations/
20260825120004_trips_and_itinerary.sql, 20260826120001_phase6_ai_itinerary.sql).

Trust boundary (same discipline as ProfilesRepository/OnboardingRepository):
the backend connects via the service-role-equivalent pool, which bypasses
RLS entirely — `is_trip_accessible()` below IS the authorization boundary
at this layer, exercised on every trip-scoped request BEFORE any read/write
(CLAUDE.md §5 "enforce authorization server-side, on every request"). RLS
(tested in tests/test_rls_security.py) remains a second, independent layer.
"""

from __future__ import annotations

import uuid
from datetime import time as time_cls
from typing import Any

from app.repositories.base import Repository


def _parse_time(value: Any) -> time_cls | None:
    """asyncpg's `time` codec requires a real `datetime.time` object, not a
    string — every item field carrying a "HH:MM" string (computed by
    business_rules or returned by the LLM's structured output) must go
    through this before being bound as a query argument."""
    if value is None or isinstance(value, time_cls):
        return value
    hh, mm = str(value).split(":")[:2]
    return time_cls(int(hh), int(mm))


_TRIP_COLUMNS = (
    "id, owner_id, title, destination, destination_lat, destination_lng, "
    "start_date, end_date, status, trip_type, budget_planned, budget_currency, "
    "generation_status, created_at, updated_at"
)

_ITEM_COLUMNS = (
    "i.id, i.trip_id, i.day_id, i.poi_id, i.sequence_order, i.planned_start, "
    "i.planned_end, i.estimated_duration_min, i.estimated_cost, i.status, "
    "i.source, i.verify_on_arrival, i.weather_flag, i.weather_alternative_suggestion, "
    "i.notes, p.name as poi_name, "
    "ST_Y(p.location::geometry) as poi_lat, ST_X(p.location::geometry) as poi_lng, "
    "p.category as poi_category, p.opening_hours as poi_opening_hours, "
    "p.avg_cost as poi_avg_cost"
)


class TripsRepository(Repository):
    # ---- trips ----

    async def create_trip(self, owner_id: str, **fields: Any) -> dict[str, Any]:
        row = await self.fetchrow(
            f"""
            insert into public.trips
                (owner_id, title, destination, destination_lat, destination_lng,
                 start_date, end_date, budget_planned, budget_currency)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            returning {_TRIP_COLUMNS};
            """,
            uuid.UUID(owner_id),
            fields["title"],
            fields["destination"],
            fields.get("destination_lat"),
            fields.get("destination_lng"),
            fields.get("start_date"),
            fields.get("end_date"),
            fields.get("budget_planned"),
            fields.get("budget_currency", "INR"),
        )
        assert row is not None
        return dict(row)

    async def is_trip_accessible(self, trip_id: str, user_id: str) -> bool:
        value = await self.fetchval(
            """
            select exists (
                select 1 from public.trips t
                where t.id = $1 and t.deleted_at is null
                  and (t.owner_id = $2
                       or exists (select 1 from public.trip_members m
                                  where m.trip_id = t.id and m.user_id = $2))
            );
            """,
            uuid.UUID(trip_id),
            uuid.UUID(user_id),
        )
        return bool(value)

    async def is_trip_owner(self, trip_id: str, user_id: str) -> bool:
        value = await self.fetchval(
            "select exists (select 1 from public.trips "
            "where id = $1 and owner_id = $2 and deleted_at is null);",
            uuid.UUID(trip_id),
            uuid.UUID(user_id),
        )
        return bool(value)

    async def get_trip(self, trip_id: str) -> dict[str, Any] | None:
        row = await self.fetchrow(
            f"select {_TRIP_COLUMNS} from public.trips where id = $1 and deleted_at is null;",
            uuid.UUID(trip_id),
        )
        return dict(row) if row else None

    async def list_trips(self, owner_id: str) -> list[dict[str, Any]]:
        rows = await self.fetch(
            f"""
            select {_TRIP_COLUMNS} from public.trips
            where (owner_id = $1
                   or exists (select 1 from public.trip_members m
                              where m.trip_id = trips.id and m.user_id = $1))
              and deleted_at is null
            order by
                case status when 'active' then 0 when 'upcoming' then 1
                             when 'draft' then 2 when 'completed' then 3 else 4 end,
                created_at desc;
            """,
            uuid.UUID(owner_id),
        )
        return [dict(row) for row in rows]

    async def update_trip(self, trip_id: str, **fields: Any) -> dict[str, Any] | None:
        sets = []
        args: list[Any] = [uuid.UUID(trip_id)]
        for i, (key, value) in enumerate(fields.items(), start=2):
            sets.append(f"{key} = ${i}")
            args.append(value)
        if not sets:
            return await self.get_trip(trip_id)
        sets.append("updated_at = now()")
        row = await self.fetchrow(
            f"update public.trips set {', '.join(sets)} where id = $1 returning {_TRIP_COLUMNS};",
            *args,
        )
        return dict(row) if row else None

    async def soft_delete_trip(self, trip_id: str) -> None:
        await self.fetchval(
            "update public.trips set deleted_at = now() where id = $1 returning id;",
            uuid.UUID(trip_id),
        )

    async def set_generation_status(self, trip_id: str, status: str) -> None:
        await self.fetchval(
            "update public.trips set generation_status = $2, updated_at = now() "
            "where id = $1 returning id;",
            uuid.UUID(trip_id),
            status,
        )

    # ---- trip_raw_notes (F4) ----

    async def create_note(self, trip_id: str, created_by: str, raw_text: str) -> dict[str, Any]:
        row = await self.fetchrow(
            """
            insert into public.trip_raw_notes (trip_id, created_by, raw_text)
            values ($1, $2, $3)
            returning id, trip_id, raw_text, extracted_places, unparsed_remainder,
                      parsed_at, created_at;
            """,
            uuid.UUID(trip_id),
            uuid.UUID(created_by),
            raw_text,
        )
        assert row is not None
        return dict(row)

    async def update_note_parsed(
        self, note_id: str, extracted_places: list[dict], unparsed_remainder: str | None
    ) -> None:
        # `str()` first: the only caller (idea_extraction_service) passes the
        # `id` straight out of `create_note`'s returned row, which asyncpg
        # hands back as an `asyncpg.pgproto.UUID` object rather than a plain
        # string — and `uuid.UUID()` calls `.replace` on its argument, so an
        # already-UUID value raised `AttributeError` and surfaced as a 500.
        # Real bug found by running the note-submission path live; it is
        # reached whether or not an LLM is configured.
        await self.fetchval(
            """
            update public.trip_raw_notes
            set extracted_places = $2::jsonb, unparsed_remainder = $3, parsed_at = now()
            where id = $1
            returning id;
            """,
            uuid.UUID(str(note_id)),
            # NOT json.dumps()-ed: the pool registers a jsonb<->dict/list
            # codec whose encoder is already json.dumps (app/db/session.py),
            # so pre-dumping stores a JSON *string* in the column and reads
            # it back as `str` — the same double-encoding bug already
            # documented for budget/disruption/group/notifications. It was
            # invisible here only because the `uuid.UUID()` crash above meant
            # this statement never ran; fixing that exposed it immediately
            # (GET /trips/{id}/notes then failed schema validation).
            extracted_places,
            unparsed_remainder,
        )

    async def list_notes(self, trip_id: str) -> list[dict[str, Any]]:
        rows = await self.fetch(
            "select id, trip_id, raw_text, extracted_places, unparsed_remainder, "
            "parsed_at, created_at from public.trip_raw_notes "
            "where trip_id = $1 order by created_at asc;",
            uuid.UUID(trip_id),
        )
        return [dict(row) for row in rows]

    # ---- itinerary (F3/F5) ----

    async def get_itinerary(self, trip_id: str) -> list[dict[str, Any]]:
        """Returns day rows, each carrying its own `items` list (already
        joined + ordered) — one round trip, not N+1 (CLAUDE.md §18)."""
        day_rows = await self.fetch(
            "select id, trip_id, day_number, date from public.itinerary_days "
            "where trip_id = $1 order by day_number asc;",
            uuid.UUID(trip_id),
        )
        item_rows = await self.fetch(
            f"select {_ITEM_COLUMNS} from public.itinerary_items i "
            "left join public.pois p on p.id = i.poi_id "
            "where i.trip_id = $1 order by i.day_id, i.sequence_order asc;",
            uuid.UUID(trip_id),
        )
        items_by_day: dict[Any, list[dict[str, Any]]] = {}
        for row in item_rows:
            items_by_day.setdefault(row["day_id"], []).append(dict(row))

        return [
            {
                "day_number": day["day_number"],
                "date": day["date"],
                "items": items_by_day.get(day["id"], []),
            }
            for day in day_rows
        ]

    async def replace_itinerary(self, trip_id: str, days: list[dict[str, Any]]) -> None:
        """Atomically replaces the entire itinerary for a trip — deleting
        `itinerary_days` cascades to `itinerary_items` (DATABASE_SCHEMA.md
        §4 `on delete cascade`). Used by F3 (fresh generation) and by F5's
        full-diff-apply path is intentionally NOT this method (see
        `apply_item_changes` below, which patches specific items in place so
        "only the relevant segment changes" holds)."""
        tid = uuid.UUID(trip_id)
        async with self.transaction() as conn:
            await conn.execute("delete from public.itinerary_days where trip_id = $1;", tid)
            for day in days:
                day_row = await conn.fetchrow(
                    "insert into public.itinerary_days (trip_id, day_number, date) "
                    "values ($1, $2, $3) returning id;",
                    tid,
                    day["day_number"],
                    day.get("date"),
                )
                day_id = day_row["id"]
                for item in day["items"]:
                    await conn.execute(
                        """
                        insert into public.itinerary_items
                            (trip_id, day_id, poi_id, sequence_order, planned_start, planned_end,
                             estimated_duration_min, estimated_cost, status, source,
                             verify_on_arrival, weather_flag, weather_alternative_suggestion, notes)
                        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14);
                        """,
                        tid,
                        day_id,
                        uuid.UUID(item["poi_id"]) if item.get("poi_id") else None,
                        item["sequence_order"],
                        _parse_time(item.get("planned_start")),
                        _parse_time(item.get("planned_end")),
                        item.get("estimated_duration_min"),
                        item.get("estimated_cost"),
                        item.get("status", "planned"),
                        item.get("source", "ai"),
                        item.get("verify_on_arrival", False),
                        item.get("weather_flag", False),
                        item.get("weather_alternative_suggestion"),
                        item.get("notes"),
                    )

    async def get_or_create_day(self, trip_id: str, day_number: int) -> str:
        tid = uuid.UUID(trip_id)
        existing = await self.fetchval(
            "select id from public.itinerary_days where trip_id = $1 and day_number = $2;",
            tid,
            day_number,
        )
        if existing is not None:
            return str(existing)
        created = await self.fetchval(
            "insert into public.itinerary_days (trip_id, day_number) values ($1, $2) returning id;",
            tid,
            day_number,
        )
        return str(created)

    async def insert_item(self, trip_id: str, day_number: int, **fields: Any) -> dict[str, Any]:
        """Adds a single new item to an existing (or newly created) day —
        used by F5 when a conversational change adds a stop, WITHOUT
        touching any other item (AI_ARCHITECTURE.md §4's "only the relevant
        segment changes, rest of plan preserved")."""
        day_id = await self.get_or_create_day(trip_id, day_number)
        new_id = await self.fetchval(
            """
            insert into public.itinerary_items
                (trip_id, day_id, poi_id, sequence_order, planned_start, planned_end,
                 estimated_duration_min, estimated_cost, status, source,
                 verify_on_arrival, weather_flag, weather_alternative_suggestion, notes)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            returning id;
            """,
            uuid.UUID(trip_id),
            uuid.UUID(day_id),
            uuid.UUID(fields["poi_id"]) if fields.get("poi_id") else None,
            fields.get("sequence_order", 0),
            _parse_time(fields.get("planned_start")),
            _parse_time(fields.get("planned_end")),
            fields.get("estimated_duration_min"),
            fields.get("estimated_cost"),
            fields.get("status", "planned"),
            fields.get("source", "ai"),
            fields.get("verify_on_arrival", False),
            fields.get("weather_flag", False),
            fields.get("weather_alternative_suggestion"),
            fields.get("notes"),
        )
        row = await self.get_item(str(new_id), trip_id)
        assert row is not None
        return row

    async def get_item(self, item_id: str, trip_id: str) -> dict[str, Any] | None:
        row = await self.fetchrow(
            f"select {_ITEM_COLUMNS} from public.itinerary_items i "
            "left join public.pois p on p.id = i.poi_id "
            "where i.id = $1 and i.trip_id = $2;",
            uuid.UUID(item_id),
            uuid.UUID(trip_id),
        )
        return dict(row) if row else None

    async def update_item(self, item_id: str, trip_id: str, **fields: Any) -> dict[str, Any] | None:
        sets = []
        args: list[Any] = [uuid.UUID(item_id), uuid.UUID(trip_id)]
        for key, value in fields.items():
            if key in ("planned_start", "planned_end"):
                value = _parse_time(value)
            args.append(value)
            sets.append(f"{key} = ${len(args)}")
        if not sets:
            return await self.get_item(item_id, trip_id)
        sets.append("updated_at = now()")
        await self.fetchval(
            f"update public.itinerary_items set {', '.join(sets)} "
            "where id = $1 and trip_id = $2 returning id;",
            *args,
        )
        return await self.get_item(item_id, trip_id)
