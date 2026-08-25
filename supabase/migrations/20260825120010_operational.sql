-- audit_logs, analytics_events — DATABASE_SCHEMA.md §12.
--
-- SCHEMA FIX APPLIED:
--   C2 (CRITICAL): audit_logs.actor_user_id now ON DELETE SET NULL (was
--   unspecified / implicit NO ACTION). Without this fix, the documented
--   account-deletion workflow (DEPLOYMENT_PLAN.md §6, "profiles row and all
--   owned data cascades per FK on delete cascade") would FAIL with a
--   foreign-key violation for any user who has ever performed an audited
--   action (e.g. a routine memory-box export, per §27's own list of
--   audited action types) — the deletion transaction would be blocked
--   entirely. The audit trail correctly survives the actor's account
--   deletion (standard practice — the row still records what happened and
--   when, only losing the joinable link to a now-deleted account).

create table public.audit_logs (
  id              uuid primary key default gen_random_uuid(),
  actor_user_id   uuid references public.profiles(id) on delete set null,  -- fixes C2
  action          text not null,
  target_type     text not null,
  target_id       uuid,
  metadata        jsonb not null default '{}',
  created_at      timestamptz not null default now()
);

alter table public.audit_logs enable row level security;

create policy "audit_logs_admin_read" on public.audit_logs
  for select using (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin')
  );

comment on table public.audit_logs is
  'Inserts: service-role only, from the backend audit-logging middleware (§27). No client INSERT policy exists.';

create table public.analytics_events (
  id            bigint generated always as identity primary key,
  user_id       uuid references public.profiles(id) on delete set null,
  event_name    text not null,
  properties    jsonb not null default '{}',
  occurred_at   timestamptz not null default now()
);

create index analytics_events_name_idx on public.analytics_events (event_name, occurred_at);

alter table public.analytics_events enable row level security;

create policy "analytics_events_admin_read" on public.analytics_events
  for select using (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin')
  );

comment on table public.analytics_events is
  'Inserts: service-role only, fire-and-forget from the analytics middleware — never blocks the primary request.';
