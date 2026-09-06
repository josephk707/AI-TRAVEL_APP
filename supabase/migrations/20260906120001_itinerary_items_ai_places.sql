-- AI-first itinerary generation (2026-09-06).
--
-- An itinerary stop may now come straight from the model's own knowledge of
-- the destination (grounded afterwards through geocoding) rather than only
-- from a pre-existing `pois` catalog row. Each stop therefore carries its
-- own place snapshot so it renders, validates (travel-time / weather) and
-- navigates (tap-to-open in Google Maps) even when no catalog row exists
-- for it. `poi_id` remains the link whenever one does exist; readers
-- coalesce `pois.*` first and fall back to these columns
-- (app/repositories/trips_repository.py `_ITEM_COLUMNS`).
--
-- `location_source` records how the coordinates were obtained:
--   poi         - matched an existing `pois` row (curated or cached)
--   places_api  - verified live via Geoapify geocoding and cached into `pois`
--   ai_estimate - only the model's approximate coordinates were available;
--                 the client labels these "approximate"
--   unresolved  - no coordinates at all; the client labels these
--                 "location not verified" and links by name only

alter table public.itinerary_items
  add column if not exists place_name text,
  add column if not exists place_area text,
  add column if not exists place_category text
    check (place_category is null
           or place_category in ('heritage', 'restaurant', 'attraction', 'nature', 'shopping', 'other')),
  add column if not exists place_lat double precision
    check (place_lat is null or (place_lat between -90 and 90)),
  add column if not exists place_lng double precision
    check (place_lng is null or (place_lng between -180 and 180)),
  add column if not exists location_source text not null default 'poi'
    check (location_source in ('poi', 'places_api', 'ai_estimate', 'unresolved'));

comment on column public.itinerary_items.place_name is
  'Model-proposed place name; authoritative only when poi_id is null (readers coalesce pois.name first).';
comment on column public.itinerary_items.location_source is
  'How this stop''s coordinates were obtained: poi | places_api | ai_estimate | unresolved.';
