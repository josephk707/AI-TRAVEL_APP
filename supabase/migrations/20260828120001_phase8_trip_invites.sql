-- Phase 8 — F19 Group/Collaborative Trip Planning (IMPLEMENTATION_BLUEPRINT.md
-- F19, API_SPECIFICATION.md §13). `trip_members` (Phase 2 migration
-- 20260825120004) already exists but its primary key is (trip_id, user_id) —
-- user_id is NOT NULL, so a row cannot be created until the invited
-- person's identity is known. `POST /trips/{trip_id}/invite` needs to
-- issue a redeemable token BEFORE that identity is known (a link/email
-- invite, per the Blueprint's "External API: None — invite links are
-- internal deep links"). This table holds that pending, not-yet-claimed
-- state; the real trip_members row is only ever created at the moment of
-- redemption (`POST /trips/invite/{token}/accept`), with invite_status
-- inserted directly as 'accepted' — this project's existing
-- is_trip_accessible() check (any trip_members row = access) is
-- therefore never exposed to a not-yet-accepted pending state, so it did
-- not need to change.

create table public.trip_invites (
  id           uuid primary key default gen_random_uuid(),
  trip_id      uuid not null references public.trips(id) on delete cascade,
  invited_by   uuid not null references public.profiles(id) on delete cascade,
  method       text not null check (method in ('link', 'email')),
  email        text,
  token        text not null unique default encode(gen_random_bytes(24), 'hex'),
  status       text not null default 'pending' check (status in ('pending', 'accepted', 'expired')),
  created_at   timestamptz not null default now(),
  expires_at   timestamptz not null default (now() + interval '14 days'),
  accepted_by  uuid references public.profiles(id) on delete set null,
  accepted_at  timestamptz,
  check (method <> 'email' or email is not null)
);

create index trip_invites_trip_idx on public.trip_invites(trip_id);
create index trip_invites_token_idx on public.trip_invites(token);

alter table public.trip_invites enable row level security;

-- Only the trip owner can see/manage the invites they issued — the
-- redemption path (GET/validate-by-token) is backend-mediated via the
-- service-role connection, never a direct client RLS read (matching the
-- trip_location_shares precedent in migration 20260825120007).
create policy "trip_invites_owner" on public.trip_invites
  for all using (
    exists (select 1 from public.trips t where t.id = trip_id and t.owner_id = auth.uid())
  );
