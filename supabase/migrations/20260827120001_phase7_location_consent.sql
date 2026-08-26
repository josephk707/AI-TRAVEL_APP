-- Phase 7 — F7 Real-Time Location Companion (BR-014): "explicit per-trip
-- opt-in consent required before any location write." No document defines
-- WHERE this consent is stored — API_SPECIFICATION.md §6 says the ping
-- endpoint "returns 403 if the trip has no active location-sharing
-- consent recorded" but no table/column for it exists anywhere in
-- DATABASE_SCHEMA.md. Documented resolution (CLAUDE.md §13): a consent
-- flag lives directly on `trips`, scoped per-trip (matching BR-014's own
-- "per-trip" wording) rather than a separate table, since it is a single
-- boolean gate with no history/multi-row shape of its own.

alter table public.trips
  add column location_sharing_consent boolean not null default false,
  add column location_sharing_consented_at timestamptz;

comment on column public.trips.location_sharing_consent is
  'F7 (BR-014): explicit per-trip opt-in required before any location_pings write. Set only via POST /trips/{id}/location/consent, never implied by trip creation.';
