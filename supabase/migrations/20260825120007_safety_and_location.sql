-- trusted_contacts, trip_location_shares, sos_events, location_pings —
-- DATABASE_SCHEMA.md §9.
--
-- SCHEMA FIX APPLIED:
--   M2 (MEDIUM): sos_events.trip_id now ON DELETE CASCADE (was unspecified).

create table public.trusted_contacts (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references public.profiles(id) on delete cascade,
  name        text not null,
  phone       text,
  email       text,
  created_at  timestamptz not null default now(),
  check (phone is not null or email is not null)
);

alter table public.trusted_contacts enable row level security;

create policy "trusted_contacts_own" on public.trusted_contacts
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create table public.trip_location_shares (
  id           uuid primary key default gen_random_uuid(),
  trip_id      uuid not null references public.trips(id) on delete cascade,
  user_id      uuid not null references public.profiles(id) on delete cascade,
  share_token  text not null unique default encode(gen_random_bytes(24), 'hex'),
  is_active    boolean not null default true,
  started_at   timestamptz not null default now(),
  expires_at   timestamptz not null
);

alter table public.trip_location_shares enable row level security;

create policy "trip_location_shares_own" on public.trip_location_shares
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

comment on table public.trip_location_shares is
  'The trusted contact viewing a share is typically NOT an app user (no auth.uid()). That read path is served by a dedicated backend endpoint validated against share_token + expires_at using the service-role key — never a client-side anon-key RLS read. See API_SPECIFICATION.md §16.';

create table public.sos_events (
  id                     uuid primary key default gen_random_uuid(),
  user_id                uuid not null references public.profiles(id) on delete cascade,
  trip_id                uuid references public.trips(id) on delete cascade,   -- fixes M2
  triggered_at           timestamptz not null default now(),
  last_known_lat         double precision,
  last_known_lng         double precision,
  location_captured_at   timestamptz,
  resolved_at            timestamptz
);

alter table public.sos_events enable row level security;

create policy "sos_events_own" on public.sos_events
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
create table public.location_pings (
  id            uuid primary key default gen_random_uuid(),
  trip_id       uuid not null references public.trips(id) on delete cascade,
  user_id       uuid not null references public.profiles(id) on delete cascade,
  location      geography(Point, 4326) not null,
  recorded_at   timestamptz not null default now()
);

create index location_pings_trip_idx on public.location_pings (trip_id, recorded_at desc);
create index location_pings_gix on public.location_pings using gist (location);

alter table public.location_pings enable row level security;

create policy "location_pings_own" on public.location_pings
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

comment on table public.location_pings is
  'Ephemeral, active-trip-only retention (PRD §23: location must not be retained indefinitely). Purge contract: see migration 20260825120012.';
