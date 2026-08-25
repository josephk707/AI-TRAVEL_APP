-- bookings, trip_recaps — DATABASE_SCHEMA.md §13.
--
-- Design-for-future stubs per BR-013 ("architect the platform to support
-- future automated hotel/flight booking... without a rebuild"). No
-- booking/payment logic is implemented anywhere this phase or the next —
-- these tables exist only so the schema is stable for Phase 13
-- (Flights, Hotels & Booking Integration) and Phase 4-equivalent product
-- work (trip recap), per this document's own §13 rationale. No fix needed;
-- ON DELETE behavior in the original schema was already fully specified.

create table public.bookings (
  id             uuid primary key default gen_random_uuid(),
  trip_id        uuid not null references public.trips(id) on delete cascade,
  user_id        uuid not null references public.profiles(id) on delete cascade,
  booking_type   text not null check (booking_type in ('hotel', 'flight', 'experience')),
  partner_name   text not null,
  partner_ref    text,
  status         text not null default 'link_out' check (status in ('link_out', 'pending', 'confirmed', 'failed', 'cancelled')),
  amount         numeric(12, 2),
  currency       text default 'INR',
  created_at     timestamptz not null default now()
);

alter table public.bookings enable row level security;

create policy "bookings_member" on public.bookings
  for all using (public.is_trip_member(trip_id)) with check (public.is_trip_member(trip_id));

create table public.trip_recaps (
  id             uuid primary key default gen_random_uuid(),
  trip_id        uuid not null references public.trips(id) on delete cascade,
  content        jsonb not null,
  generated_at   timestamptz not null default now()
);

alter table public.trip_recaps enable row level security;

create policy "trip_recaps_member" on public.trip_recaps
  for all using (public.is_trip_member(trip_id)) with check (public.is_trip_member(trip_id));
