-- memory_items, collections, collection_items, favorites, reviews —
-- DATABASE_SCHEMA.md §6.
--
-- SCHEMA FIXES APPLIED:
--   H6 (HIGH): memory_items RLS split from a single permissive
--     `for all using (is_trip_member)` into shared SELECT (any trip member —
--     "gallery" viewing is intended) plus author-or-trip-owner-only
--     INSERT/UPDATE/DELETE. Previously any group-trip member could delete
--     another member's uploaded photos, contradicting §43.3's "never
--     surprise the user with unannounced data loss" promise.
--   M2 (MEDIUM): reviews.trip_id now ON DELETE CASCADE (was unspecified);
--     reviews.moderated_by now ON DELETE SET NULL (was unspecified).

create table public.memory_items (
  id                        uuid primary key default gen_random_uuid(),
  trip_id                   uuid not null references public.trips(id) on delete cascade,
  user_id                   uuid not null references public.profiles(id) on delete cascade,
  item_type                 text not null check (item_type in ('photo', 'video', 'note')),
  storage_path              text,
  caption                   text,
  taken_at                  timestamptz,
  uploaded_at               timestamptz not null default now(),
  retention_expires_at      timestamptz not null default (now() + interval '12 months'),
  expiry_reminder_sent_at   timestamptz,
  downloaded_at             timestamptz,
  deleted_at                timestamptz
);

create index memory_items_trip_idx on public.memory_items (trip_id);
create index memory_items_expiry_idx on public.memory_items (retention_expires_at) where deleted_at is null;

alter table public.memory_items enable row level security;

-- Shared viewing: any trip member can see the trip's memory-box gallery.
create policy "memory_items_select_member" on public.memory_items
  for select using (public.is_trip_member(trip_id));

-- Uploads: any trip member, but only claiming their own authorship.
create policy "memory_items_insert_own" on public.memory_items
  for insert with check (public.is_trip_member(trip_id) and user_id = auth.uid());

-- Mutation restricted to the uploader or the trip owner (fixes H6).
create policy "memory_items_update_author_or_owner" on public.memory_items
  for update using (
    user_id = auth.uid()
    or exists (select 1 from public.trips t where t.id = trip_id and t.owner_id = auth.uid())
  );

create policy "memory_items_delete_author_or_owner" on public.memory_items
  for delete using (
    user_id = auth.uid()
    or exists (select 1 from public.trips t where t.id = trip_id and t.owner_id = auth.uid())
  );

comment on column public.memory_items.deleted_at is
  'Explicit user deletion only. The retention job (docs/DEPLOYMENT_PLAN.md §5) NEVER sets this — see the retention-contract functions in migration 20260825120012.';

-- ---------------------------------------------------------------------------
create table public.collections (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references public.profiles(id) on delete cascade,
  name        text not null,
  created_at  timestamptz not null default now(),
  unique (user_id, name)
);

create table public.collection_items (
  collection_id  uuid not null references public.collections(id) on delete cascade,
  poi_id         uuid not null references public.pois(id) on delete cascade,
  added_at       timestamptz not null default now(),
  primary key (collection_id, poi_id)
);

create table public.favorites (
  user_id     uuid not null references public.profiles(id) on delete cascade,
  poi_id      uuid not null references public.pois(id) on delete cascade,
  created_at  timestamptz not null default now(),
  primary key (user_id, poi_id)
);

alter table public.collections enable row level security;
alter table public.collection_items enable row level security;
alter table public.favorites enable row level security;

create policy "collections_own" on public.collections
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "collection_items_own" on public.collection_items
  for all using (
    exists (select 1 from public.collections c where c.id = collection_id and c.user_id = auth.uid())
  ) with check (
    exists (select 1 from public.collections c where c.id = collection_id and c.user_id = auth.uid())
  );

create policy "favorites_own" on public.favorites
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
create table public.reviews (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references public.profiles(id) on delete cascade,
  poi_id         uuid not null references public.pois(id) on delete cascade,
  trip_id        uuid not null references public.trips(id) on delete cascade,      -- fixes M2
  rating         smallint not null check (rating between 1 and 5),
  review_text    text,
  status         text not null default 'pending' check (status in ('pending', 'published', 'rejected')),
  moderated_by   uuid references public.profiles(id) on delete set null,           -- fixes M2
  moderated_at   timestamptz,
  created_at     timestamptz not null default now()
);

create index reviews_poi_idx on public.reviews (poi_id) where status = 'published';

alter table public.reviews enable row level security;

create policy "reviews_read_published" on public.reviews
  for select using (status = 'published' or user_id = auth.uid());

create policy "reviews_insert_own" on public.reviews
  for insert with check (
    auth.uid() = user_id
    and exists (
      select 1 from public.trips t
      where t.id = trip_id and t.owner_id = auth.uid() and t.status = 'completed'
    )
  );
