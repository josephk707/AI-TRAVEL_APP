"""
Repository for `pois` — F6 Maps & Navigation
(supabase/migrations/20260825120003_pois_and_heritage.sql,
20260825120017_pois_maps_navigation.sql).

`pois` is shared reference/business data (not user-owned), so unlike
`OnboardingRepository`/`ProfilesRepository` these methods take no user id —
every authenticated traveller reads the same catalog (RLS: `pois_read_all`
permits any `authenticated` role to SELECT). Writes here are the backend's
own cache-population path (caching a live Google Places result), never a
client-supplied row — the client only ever reaches these through the
`/v1/pois/*` endpoints, never with direct table access.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.repositories.base import Repository

_POI_COLUMNS = (
    "id, name, category, "
    "ST_Y(location::geometry) as lat, ST_X(location::geometry) as lng, "
    "address, city, region, country, opening_hours, avg_cost, source, "
    "external_ref, is_heritage_flagship, created_at, updated_at"
)


class PoisRepository(Repository):
    async def get_by_id(self, poi_id: str) -> dict[str, Any] | None:
        row = await self.fetchrow(
            f"select {_POI_COLUMNS} from public.pois where id = $1;",
            uuid.UUID(poi_id),
        )
        return dict(row) if row else None

    async def get_by_external_ref(self, external_ref: str) -> dict[str, Any] | None:
        row = await self.fetchrow(
            f"select {_POI_COLUMNS} from public.pois where external_ref = $1;",
            external_ref,
        )
        return dict(row) if row else None

    async def search_text(
        self, query: str, category: str | None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Local-cache text search — matches on name/city/region, case
        insensitive. This is the first place `poi_service.search()` looks;
        only when it returns too few results does the service fall back to
        a live Google Places call."""
        rows = await self.fetch(
            f"""
            select {_POI_COLUMNS} from public.pois
            where (name ilike '%' || $1 || '%' or city ilike '%' || $1 || '%'
                   or region ilike '%' || $1 || '%')
              and ($2::text is null or category = $2)
            order by is_heritage_flagship desc, name asc
            limit $3;
            """,
            query,
            category,
            limit,
        )
        return [dict(row) for row in rows]

    async def search_nearby(
        self, lat: float, lng: float, radius_m: float, category: str | None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Real geospatial query against the GiST index (`pois_location_gix`)
        via `ST_DWithin`, per `API_SPECIFICATION.md` §5's documented
        contract for `GET /pois/nearby`."""
        rows = await self.fetch(
            f"""
            select {_POI_COLUMNS} from public.pois
            where ST_DWithin(location, ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography, $3)
              and ($4::text is null or category = $4)
            order by location <-> ST_SetSRID(ST_MakePoint($2, $1), 4326)::geography
            limit $5;
            """,
            lat,
            lng,
            radius_m,
            category,
            limit,
        )
        return [dict(row) for row in rows]

    async def upsert_from_places_api(self, poi: dict[str, Any]) -> dict[str, Any]:
        """Caches one Google-Places-sourced POI. `external_ref` carries the
        uniqueness constraint added in migration 20260825120017, so a
        repeated search for the same real-world place updates the existing
        cached row (fresher address/hours) rather than creating a
        duplicate."""
        row = await self.fetchrow(
            f"""
            insert into public.pois
                (name, category, location, address, city, region,
                 opening_hours, source, external_ref)
            values
                ($1, $2, ST_SetSRID(ST_MakePoint($4, $3), 4326)::geography,
                 $5, $6, $7, $8::jsonb, 'places_api', $9)
            on conflict (external_ref) do update set
                name = excluded.name,
                category = excluded.category,
                location = excluded.location,
                address = excluded.address,
                city = excluded.city,
                region = excluded.region,
                opening_hours = excluded.opening_hours,
                updated_at = now()
            returning {_POI_COLUMNS};
            """,
            poi["name"],
            poi["category"],
            poi["lat"],
            poi["lng"],
            poi.get("address"),
            poi.get("city"),
            poi.get("region"),
            poi.get("opening_hours"),
            poi["external_ref"],
        )
        assert row is not None
        return dict(row)
