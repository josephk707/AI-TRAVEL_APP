-- trips, trip_members, trip_preferences, trip_raw_notes, itinerary_days,
-- itinerary_items — DATABASE_SCHEMA.md §4.
--
-- SCHEMA FIXES APPLIED:
--   M2 (MEDIUM): itinerary_items.poi_id now ON DELETE SET NULL (was
--     unspecified). Nullable column — a deleted POI orphans the reference
--     rather than blocking the delete or destroying itinerary history.
--   H6 (HIGH):   trip_raw_notes gains a `created_by` column (previously had
--     no author-tracking column at all, which made a correct per-author RLS
--     policy impossible to write). See docs/PHASE_STATUS.md Phase 2 section
--     for why this was necessary before H6's RLS fix could be applied.

create table public.trips (
  id                 uuid primary key default gen_random_uuid(),
  owner_id           uuid not null references public.profiles(id) on delete cascade,
  title              text not null,
  destination        text not null,
  destination_lat    double precision,
  destination_lng    double precision,
  start_date         date,
  end_date           date,
  status             text not null default 'draft'
                       check (status in ('draft', 'upcoming', 'active', 'completed', 'cancelled')),
  trip_type          text not null default 'solo' check (trip_type in ('solo', 'group', 'quick_plan')),
  budget_planned     numeric(12, 2),
  budget_currency    text not null default 'INR',
  generation_status  text not null default 'none'
                       check (generation_status in ('none', 'pending', 'succeeded', 'fallback_used', 'failed')),
  deleted_at         timestamptz,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

create index trips_owner_idx on public.trips (owner_id) where deleted_at is null;
create index trips_status_idx on public.trips (status);

alter table public.trips enable row level security;

-- ---------------------------------------------------------------------------
-- trip_members (product-Phase-2 "Group Planning" feature; table exists from
-- this migration because the RLS policy on `trips` itself references it —
-- see docs/ARCHITECTURE_REVIEW.md §2.14. No Phase-2-product application code
-- writes to it yet; this is schema-stability plumbing only.)
-- ---------------------------------------------------------------------------
create table public.trip_members (
  trip_id        uuid not null references public.trips(id) on delete cascade,
  user_id        uuid not null references public.profiles(id) on delete cascade,
  role           text not null default 'member' check (role in ('organiser', 'member')),
  invite_status  text not null default 'invited'
                   check (invite_status in ('invited', 'accepted', 'declined', 'no_response')),
  invited_at     timestamptz not null default now(),
  responded_at   timestamptz,
  primary key (trip_id, user_id)
);

comment on table public.trip_members is
  'Exists from Phase 2 (data layer) migration for RLS/schema stability on trips; not written to by any product feature until group-planning (Phase 2 product roadmap) ships.';

alter table public.trip_members enable row level security;

create policy "trip_members_select" on public.trip_members
  for select using (
    auth.uid() = user_id
    or exists (select 1 from public.trips t where t.id = trip_id and t.owner_id = auth.uid())
  );

-- Now that trip_members exists, define the trips policies that depend on it.
create policy "trips_select_member" on public.trips
  for select using (
    auth.uid() = owner_id
    or exists (select 1 from public.trip_members m where m.trip_id = trips.id and m.user_id = auth.uid())
  );

create policy "trips_write_owner" on public.trips
  for all using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);

-- ---------------------------------------------------------------------------
-- Shared helper: "is this user a member (owner or accepted/invited member)
-- of this trip?" Reused by every trip-scoped child table's RLS policy.
-- ---------------------------------------------------------------------------
create function public.is_trip_member(p_trip_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.trips t
    where t.id = p_trip_id
      and (
        t.owner_id = auth.uid()
        or exists (select 1 from public.trip_members m where m.trip_id = t.id and m.user_id = auth.uid())
      )
  );
$$;

-- ---------------------------------------------------------------------------
-- trip_preferences (product-Phase-2 group reconciliation input, FR-012)
-- ---------------------------------------------------------------------------
create table public.trip_preferences (
  trip_id       uuid not null references public.trips(id) on delete cascade,
  user_id       uuid not null references public.profiles(id) on delete cascade,
  interests     jsonb not null default '[]',
  budget_max    numeric(12, 2),
  constraints   jsonb not null default '{}',
  submitted_at  timestamptz not null default now(),
  primary key (trip_id, user_id)
);

alter table public.trip_preferences enable row level security;

create policy "trip_preferences_own_or_organiser" on public.trip_preferences
  for select using (
    auth.uid() = user_id
    or exists (select 1 from public.trips t where t.id = trip_id and t.owner_id = auth.uid())
  );

create policy "trip_preferences_write_own" on public.trip_preferences
  for insert with check (auth.uid() = user_id and public.is_trip_member(trip_id));

create policy "trip_preferences_update_own" on public.trip_preferences
  for update using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- trip_raw_notes (FR-005) — H6 fix: added created_by so DELETE/UPDATE can be
-- restricted to the author (or trip owner), matching the same
-- shared-view/author-restricted-write pattern applied across this migration
-- set. Nullable because pre-fix rows (none exist yet in a fresh schema, but
-- future imports/edge cases) should not be forced to have an author.
-- ---------------------------------------------------------------------------
create table public.trip_raw_notes (
  id                  uuid primary key default gen_random_uuid(),
  trip_id             uuid not null references public.trips(id) on delete cascade,
  created_by          uuid references public.profiles(id) on delete set null,
  raw_text            text not null,
  extracted_places    jsonb,
  unparsed_remainder  text,
  parsed_at           timestamptz,
  created_at          timestamptz not null default now()
);

alter table public.trip_raw_notes enable row level security;

create policy "trip_raw_notes_select" on public.trip_raw_notes
  for select using (public.is_trip_member(trip_id));

create policy "trip_raw_notes_insert" on public.trip_raw_notes
  for insert with check (
    public.is_trip_member(trip_id)
    and (created_by = auth.uid() or created_by is null)
  );

create policy "trip_raw_notes_update_delete_author_or_owner" on public.trip_raw_notes
  for update using (
    created_by = auth.uid()
    or exists (select 1 from public.trips t where t.id = trip_id and t.owner_id = auth.uid())
  );

create policy "trip_raw_notes_delete_author_or_owner" on public.trip_raw_notes
  for delete using (
    created_by = auth.uid()
    or exists (select 1 from public.trips t where t.id = trip_id and t.owner_id = auth.uid())
  );

-- ---------------------------------------------------------------------------
-- itinerary_days / itinerary_items
-- ---------------------------------------------------------------------------
create table public.itinerary_days (
  id          uuid primary key default gen_random_uuid(),
  trip_id     uuid not null references public.trips(id) on delete cascade,
  day_number  smallint not null,
  date        date,
  unique (trip_id, day_number)
);

alter table public.itinerary_days enable row level security;

create policy "itinerary_days_member" on public.itinerary_days
  for all using (public.is_trip_member(trip_id))
  with check (public.is_trip_member(trip_id));

create table public.itinerary_items (
  id                       uuid primary key default gen_random_uuid(),
  trip_id                  uuid not null references public.trips(id) on delete cascade,
  day_id                   uuid not null references public.itinerary_days(id) on delete cascade,
  poi_id                   uuid references public.pois(id) on delete set null,  -- fixes M2
  sequence_order           smallint not null,
  planned_start            time,
  planned_end              time,
  estimated_duration_min   smallint,
  estimated_cost           numeric(10, 2),
  status                   text not null default 'planned'
                             check (status in ('planned', 'confirmed', 'skipped', 'completed')),
  source                   text not null default 'ai' check (source in ('ai', 'user', 'imported')),
  verify_on_arrival        boolean not null default false,
  notes                    text,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

create index itinerary_items_trip_idx on public.itinerary_items (trip_id);
create index itinerary_items_day_idx on public.itinerary_items (day_id);

alter table public.itinerary_items enable row level security;

create policy "itinerary_items_member" on public.itinerary_items
  for all using (public.is_trip_member(trip_id))
  with check (public.is_trip_member(trip_id));
