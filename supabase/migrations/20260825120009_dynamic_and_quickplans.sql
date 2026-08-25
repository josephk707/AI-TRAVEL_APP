-- weather_cache, disruption_events, quick_plans, quick_plan_items —
-- DATABASE_SCHEMA.md §11.
--
-- SCHEMA FIX APPLIED:
--   M2 (MEDIUM): quick_plan_items.poi_id now ON DELETE CASCADE (was
--   unspecified) — quick plans are low-stakes/ephemeral, so a deleted POI
--   should simply drop from the plan rather than block the POI's deletion.

create table public.weather_cache (
  location_key  text primary key,
  forecast      jsonb not null,
  fetched_at    timestamptz not null default now(),
  expires_at    timestamptz not null
);

comment on table public.weather_cache is
  'No RLS: read/written via backend service only (service-role key), never client-exposed.';

create table public.disruption_events (
  id                   uuid primary key default gen_random_uuid(),
  trip_id              uuid not null references public.trips(id) on delete cascade,
  itinerary_item_id    uuid references public.itinerary_items(id) on delete cascade,
  trigger_type         text not null
                         check (trigger_type in ('weather', 'closure', 'delay', 'off_route', 'missed_activity', 'budget_overrun', 'schedule_change', 'manual_request')),
  detected_at          timestamptz not null default now(),
  proposal             jsonb not null,
  status               text not null default 'proposed' check (status in ('proposed', 'accepted', 'dismissed')),
  resolved_at          timestamptz
);

alter table public.disruption_events enable row level security;

create policy "disruption_events_member" on public.disruption_events
  for all using (public.is_trip_member(trip_id)) with check (public.is_trip_member(trip_id));

create table public.quick_plans (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid not null references public.profiles(id) on delete cascade,
  time_available_min    smallint,
  budget                numeric(10, 2),
  occasion              text,
  generated_at          timestamptz not null default now()
);

create table public.quick_plan_items (
  quick_plan_id    uuid not null references public.quick_plans(id) on delete cascade,
  poi_id           uuid not null references public.pois(id) on delete cascade,   -- fixes M2
  sequence_order   smallint not null,
  primary key (quick_plan_id, poi_id)
);

alter table public.quick_plans enable row level security;
alter table public.quick_plan_items enable row level security;

create policy "quick_plans_own" on public.quick_plans
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "quick_plan_items_own" on public.quick_plan_items
  for all using (
    exists (select 1 from public.quick_plans q where q.id = quick_plan_id and q.user_id = auth.uid())
  ) with check (
    exists (select 1 from public.quick_plans q where q.id = quick_plan_id and q.user_id = auth.uid())
  );
