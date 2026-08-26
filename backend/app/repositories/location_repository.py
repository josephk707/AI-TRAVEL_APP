"""Repository for `location_pings` + the F7 consent flag on `trips`
(DATABASE_SCHEMA.md §9, migration 20260827120001)."""

from __future__ import annotations

import uuid
from typing import Any

from app.repositories.base import Repository


class LocationRepository(Repository):
    async def get_consent(self, trip_id: str) -> bool:
        value = await self.fetchval(
            "select location_sharing_consent from public.trips where id = $1;", uuid.UUID(trip_id)
        )
        return bool(value)

    async def set_consent(self, trip_id: str, consent: bool) -> None:
        await self.fetchval(
            """
            update public.trips
            set location_sharing_consent = $2,
                location_sharing_consented_at = case
                    when $2 then now() else location_sharing_consented_at
                end
            where id = $1
            returning id;
            """,
            uuid.UUID(trip_id),
            consent,
        )

    async def record_ping(self, trip_id: str, user_id: str, lat: float, lng: float) -> str:
        ping_id = await self.fetchval(
            """
            insert into public.location_pings (trip_id, user_id, location)
            values ($1, $2, ST_SetSRID(ST_MakePoint($4, $3), 4326)::geography)
            returning id;
            """,
            uuid.UUID(trip_id),
            uuid.UUID(user_id),
            lat,
            lng,
        )
        return str(ping_id)

    async def find_nearby_planned_item(
        self, trip_id: str, lat: float, lng: float, radius_m: float = 200.0
    ) -> dict[str, Any] | None:
        """The closest not-yet-completed itinerary item within the arrival
        geofence radius, or None. Real PostGIS `ST_DWithin`/distance query."""
        row = await self.fetchrow(
            """
            select i.id as item_id, i.poi_id, p.name as poi_name,
                   ST_Distance(
                       p.location, ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography
                   ) as distance_m
            from public.itinerary_items i
            join public.pois p on p.id = i.poi_id
            where i.trip_id = $1
              and i.status in ('planned', 'confirmed')
              and ST_DWithin(
                  p.location, ST_SetSRID(ST_MakePoint($3, $2), 4326)::geography, $4
              )
            order by distance_m asc
            limit 1;
            """,
            uuid.UUID(trip_id),
            lat,
            lng,
            radius_m,
        )
        return dict(row) if row else None
