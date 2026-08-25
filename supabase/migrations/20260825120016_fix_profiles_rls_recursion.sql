-- Fixes infinite RLS recursion in `profiles_select_own`, found live by
-- Phase 3's tests/test_rls_security.py cross-user `profiles` isolation
-- tests (added because no API endpoint exercises another user's profile
-- row, so RLS was previously untested at the data layer for this table).
--
-- The admin-check branch of profiles_select_own queried public.profiles
-- itself:
--   exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin')
-- Evaluating that subquery re-invokes profiles_select_own for the SAME
-- table, which needs to evaluate the admin-check branch again, forming an
-- unbounded cycle — Postgres detects this as InvalidObjectDefinitionError
-- ("infinite recursion detected in policy for relation profiles"), which
-- broke EVERY select against profiles under a real `authenticated` role,
-- not just the admin path. Same root cause and same fix pattern as
-- migration 20260825120015's is_trip_member(): a SECURITY DEFINER helper
-- function evaluates the admin check with RLS bypassed (function-owner
-- privilege), breaking the cycle.

create function public.is_admin(check_user_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.profiles where id = check_user_id and role = 'admin'
  );
$$;

comment on function public.is_admin(uuid) is
  'SECURITY DEFINER helper so RLS policies can check admin status without recursively re-invoking profiles_select_own on public.profiles.';

drop policy "profiles_select_own" on public.profiles;

create policy "profiles_select_own" on public.profiles
  for select using (
    auth.uid() = id
    or public.is_admin(auth.uid())
  );
