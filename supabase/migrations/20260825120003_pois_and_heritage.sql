-- pois, heritage_content, heritage_content_embeddings, phrasebook_entries —
-- DATABASE_SCHEMA.md §5.
--
-- Created before trips_and_itinerary because itinerary_items.poi_id
-- references pois(id).
--
-- SCHEMA FIXES APPLIED:
--   L11 (LOW): added admin UPDATE/DELETE policies for pois and
--     heritage_content (original schema only had INSERT for admin).
--   L9  (LOW): heritage_content_embeddings no longer grants a client SELECT
--     policy — raw embedding vectors/chunk text are service-role-only.
--     Clients get narration content exclusively through the backend's
--     GET /heritage/{poi_id}/narration endpoint (AI_ARCHITECTURE.md §5),
--     which already reads via the service-role key.

create table public.pois (
  id                     uuid primary key default gen_random_uuid(),
  name                   text not null,
  category               text not null
                           check (category in ('heritage', 'restaurant', 'attraction', 'nature', 'shopping', 'other')),
  location               geography(Point, 4326) not null,
  address                text,
  city                   text,
  region                 text,
  country                text not null default 'India',
  opening_hours          jsonb,
  avg_cost               numeric(10, 2),
  source                 text not null default 'curated' check (source in ('curated', 'places_api')),
  external_ref           text,
  is_heritage_flagship   boolean not null default false,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);

create index pois_location_gix on public.pois using gist (location);
create index pois_category_idx on public.pois (category);

alter table public.pois enable row level security;

create policy "pois_read_all" on public.pois
  for select using (auth.role() = 'authenticated');

create policy "pois_write_admin" on public.pois
  for insert with check (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin')
  );

create policy "pois_update_admin" on public.pois
  for update using (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin')
  );

create policy "pois_delete_admin" on public.pois
  for delete using (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin')
  );

-- ---------------------------------------------------------------------------
create table public.heritage_content (
  id               uuid primary key default gen_random_uuid(),
  poi_id           uuid not null references public.pois(id) on delete cascade,
  layer            text not null check (layer in ('overview', 'deep')),
  section_title    text not null,
  body_text        text not null,
  source_citation  text not null,
  language         text not null default 'en',
  version          integer not null default 1,
  verified_by      uuid references public.profiles(id) on delete set null,
  verified_at      timestamptz,
  is_published     boolean not null default false,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create index heritage_content_poi_idx on public.heritage_content (poi_id) where is_published;

alter table public.heritage_content enable row level security;

create policy "heritage_content_read_published" on public.heritage_content
  for select using (is_published and auth.role() = 'authenticated');

create policy "heritage_content_write_admin" on public.heritage_content
  for insert with check (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin')
  );

create policy "heritage_content_update_admin" on public.heritage_content
  for update using (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin')
  );

create policy "heritage_content_delete_admin" on public.heritage_content
  for delete using (
    exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin')
  );

-- ---------------------------------------------------------------------------
create table public.heritage_content_embeddings (
  id                    uuid primary key default gen_random_uuid(),
  heritage_content_id   uuid not null references public.heritage_content(id) on delete cascade,
  chunk_index           smallint not null,
  chunk_text            text not null,
  embedding             vector(1536) not null,
  created_at            timestamptz not null default now()
);

create index heritage_embeddings_ivfflat on public.heritage_content_embeddings
  using ivfflat (embedding vector_cosine_ops) with (lists = 100);

alter table public.heritage_content_embeddings enable row level security;

-- No client-facing policy at all (fixes L9): default-deny for anon/authenticated.
-- Only the service-role key (which bypasses RLS) reads/writes this table,
-- via the backend's RAG retrieval step.
comment on table public.heritage_content_embeddings is
  'Service-role-only access (no client RLS policy, by design — fixes ARCHITECTURE_REVIEW.md L9). Clients get narration content only through the backend API, never direct table reads.';

-- ---------------------------------------------------------------------------
create table public.phrasebook_entries (
  id                       uuid primary key default gen_random_uuid(),
  region                   text not null,
  language_code            text not null,
  category                 text not null,
  phrase_en                text not null,
  phrase_local_script      text not null,
  phrase_transliteration   text not null,
  audio_url                text,
  created_at               timestamptz not null default now()
);

create index phrasebook_region_idx on public.phrasebook_entries (region, language_code);

alter table public.phrasebook_entries enable row level security;

create policy "phrasebook_read_all" on public.phrasebook_entries
  for select using (auth.role() = 'authenticated');
