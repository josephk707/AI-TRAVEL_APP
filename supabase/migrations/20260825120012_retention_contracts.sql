-- Retention-contract functions — DATABASE_SCHEMA.md §6 (memory_items) and §9
-- (location_pings), and this phase's explicit instruction (§10):
-- "establish the documented contract but do not prematurely build unrelated
-- infrastructure" (i.e. no cron/scheduler here — that is
-- DEPLOYMENT_PLAN.md §5's job, a Deployment-phase concern).
--
-- These functions give a future scheduled job (or, for now, a manual/test
-- invocation) a single, correct, already-reviewed source of truth for
-- "what needs action" — rather than each caller re-deriving the retention
-- predicate ad hoc. Both are read-only: neither function ever writes
-- deleted_at, matching the hard rule that the reminder job "NEVER sets
-- deleted_at" (DATABASE_SCHEMA.md §6).
--
-- Restricted to service_role: these scan across all users' data, which is
-- exactly the kind of operation that must never be reachable by a regular
-- authenticated client, even indirectly.

create function public.memory_items_due_for_reminder()
returns setof public.memory_items
language sql
stable
security definer
set search_path = public
as $$
  select *
  from public.memory_items
  where deleted_at is null
    and expiry_reminder_sent_at is null
    and retention_expires_at - now() < interval '14 days';
$$;

comment on function public.memory_items_due_for_reminder() is
  'Retention contract (DATABASE_SCHEMA.md §6): items within 14 days of retention_expires_at with no reminder sent yet. Caller is responsible for sending the reminder notification and stamping expiry_reminder_sent_at — this function never mutates data.';

create function public.location_pings_due_for_purge()
returns setof public.location_pings
language sql
stable
security definer
set search_path = public
as $$
  select lp.*
  from public.location_pings lp
  join public.trips t on t.id = lp.trip_id
  where t.status in ('completed', 'cancelled')
    and lp.recorded_at < now() - interval '7 days';
$$;

comment on function public.location_pings_due_for_purge() is
  'Retention contract (DATABASE_SCHEMA.md §9): pings on a completed/cancelled trip older than 7 days. This is a genuine hard-delete candidate list (not soft-delete) — caller is responsible for the actual DELETE.';

revoke execute on function public.memory_items_due_for_reminder() from public;
revoke execute on function public.location_pings_due_for_purge() from public;
grant execute on function public.memory_items_due_for_reminder() to service_role;
grant execute on function public.location_pings_due_for_purge() to service_role;
