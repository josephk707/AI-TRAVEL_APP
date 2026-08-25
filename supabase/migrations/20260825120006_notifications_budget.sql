-- notifications, device_push_tokens, budget_expenses — DATABASE_SCHEMA.md §7-8.
--
-- SCHEMA FIX APPLIED:
--   H6 (HIGH): budget_expenses RLS split the same way as memory_items and
--   trip_raw_notes (see migrations 20260825120005 / 20260825120004) — shared
--   viewing for any trip member, mutation restricted to the logger or the
--   trip owner. A group member should be able to see the shared trip budget,
--   but not silently edit or delete another member's logged expense.

create table public.notifications (
  id                   uuid primary key default gen_random_uuid(),
  user_id              uuid not null references public.profiles(id) on delete cascade,
  trip_id              uuid references public.trips(id) on delete cascade,
  type                 text not null
                         check (type in ('arrival', 'disruption', 'memory_expiry', 'sos', 'group_invite', 'reminder', 'system')),
  title                text not null,
  body                 text not null,
  payload              jsonb not null default '{}',
  read_at              timestamptz,
  delivered_channels   text[] not null default '{}',
  created_at           timestamptz not null default now()
);

create index notifications_user_idx on public.notifications (user_id, read_at);

alter table public.notifications enable row level security;

create policy "notifications_own" on public.notifications
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create table public.device_push_tokens (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references public.profiles(id) on delete cascade,
  expo_push_token  text not null unique,
  platform         text not null check (platform in ('ios', 'android')),
  created_at       timestamptz not null default now()
);

alter table public.device_push_tokens enable row level security;

create policy "device_push_tokens_own" on public.device_push_tokens
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
create table public.budget_expenses (
  id          uuid primary key default gen_random_uuid(),
  trip_id     uuid not null references public.trips(id) on delete cascade,
  user_id     uuid not null references public.profiles(id) on delete cascade,
  category    text not null,
  amount      numeric(10, 2) not null check (amount >= 0),
  currency    text not null default 'INR',
  split_with  jsonb,   -- Phase 2 (product roadmap): [{"user_id": "...", "share": 0.5}, ...]
  logged_at   timestamptz not null default now()
);

create index budget_expenses_trip_idx on public.budget_expenses (trip_id);

comment on column public.budget_expenses.split_with is
  'Reserved for product-roadmap Phase 2 group expense splitting (IMPLEMENTATION_BLUEPRINT.md F23). Column exists now for schema stability; not populated by any Phase-1-scope feature.';

alter table public.budget_expenses enable row level security;

create policy "budget_expenses_select_member" on public.budget_expenses
  for select using (public.is_trip_member(trip_id));

create policy "budget_expenses_insert_own" on public.budget_expenses
  for insert with check (public.is_trip_member(trip_id) and user_id = auth.uid());

create policy "budget_expenses_update_author_or_owner" on public.budget_expenses
  for update using (
    user_id = auth.uid()
    or exists (select 1 from public.trips t where t.id = trip_id and t.owner_id = auth.uid())
  );

create policy "budget_expenses_delete_author_or_owner" on public.budget_expenses
  for delete using (
    user_id = auth.uid()
    or exists (select 1 from public.trips t where t.id = trip_id and t.owner_id = auth.uid())
  );
