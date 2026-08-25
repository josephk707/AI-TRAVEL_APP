-- Fix: infinite RLS recursion between trips and trip_members — found by the
-- live RLS security test suite (tests/test_rls_security.py) against the
-- real database, not by static review. This bug was present in
-- DATABASE_SCHEMA.md's original design (copied into migration
-- 20260825120004) and was not among the 35 findings in
-- ARCHITECTURE_REVIEW.md — genuinely new, discovered only by executing
-- real cross-user queries.
--
-- Root cause: `trips_select_member`'s USING clause queries trip_members
-- directly (a plain, non-privileged subquery), which triggers
-- trip_members's own RLS policy (`trip_members_select`), which queries
-- trips directly, which re-triggers `trips_select_member` — Postgres
-- detects this as unbounded recursion and raises
-- InvalidObjectDefinitionError ("infinite recursion detected in policy for
-- relation trips") for EVERY query against either table under a normal
-- (non-owner) role, not just pathological cases.
--
-- Fix: route the cross-table check through public.is_trip_member(), a
-- SECURITY DEFINER function owned by the table owner. Postgres exempts
-- table owners from RLS by default (no FORCE ROW LEVEL SECURITY is set
-- anywhere in this schema), so is_trip_member()'s internal queries against
-- trips/trip_members run RLS-free and terminate immediately instead of
-- re-entering either policy — this is the standard, documented pattern for
-- breaking exactly this class of cross-table RLS cycle.

drop policy if exists "trips_select_member" on public.trips;

create policy "trips_select_member" on public.trips
  for select using (
    auth.uid() = owner_id
    or public.is_trip_member(id)
  );

comment on policy "trips_select_member" on public.trips is
  'Uses is_trip_member() (SECURITY DEFINER, RLS-bypassing) rather than a raw subquery into trip_members, specifically to avoid the recursion fixed in migration 20260825120015. Do not replace with an inline exists() subquery.';
