-- profiles, interests, profile_interests — DATABASE_SCHEMA.md §3.
--
-- SCHEMA FIXES APPLIED (see docs/ARCHITECTURE_REVIEW.md, resolutions documented
-- in docs/PHASE_STATUS.md Phase 2 section and docs/DATABASE_SCHEMA.md changelog):
--   C1 (CRITICAL): added `pace` column — FR-003 explicitly lists "pace" as a
--     required onboarding input; the original schema omitted it entirely.
--   M2 (MEDIUM):   profile_interests.interest_id now has an explicit
--     ON DELETE CASCADE (was previously unspecified / implicit NO ACTION).
--   H1 (HIGH):     resolved in favor of DB-trigger-based profile provisioning
--     (matches DATABASE_SCHEMA.md's and IMPLEMENTATION_BLUEPRINT.md §1.3's own
--     stated design). The trigger below is the actual, real implementation of
--     that design, not just a description of intent. API_SPECIFICATION.md §2's
--     `POST /auth/session/bootstrap` should be understood, once Phase 3 wires
--     up auth, as an idempotent "load profile" call (no-op if the trigger
--     already created the row) — that document is not modified this phase
--     since API/auth work is out of scope, but the discrepancy is recorded
--     here and in PHASE_STATUS.md so Phase 3 addresses it deliberately.

create table public.profiles (
  id                       uuid primary key references auth.users(id) on delete cascade,
  display_name             text,
  avatar_url               text,
  home_region              text,               -- seeds default local-language phrasebook (FR-009)
  travel_style             text,               -- e.g. 'relaxed' | 'packed' | 'balanced' (onboarding, FR-003)
  pace                     text check (pace in ('relaxed', 'balanced', 'packed')),  -- FR-003 input; fixes C1
  budget_bracket           text,               -- e.g. 'budget' | 'mid' | 'premium'
  role                     text not null default 'traveller' check (role in ('traveller', 'admin')),
  onboarding_completed_at  timestamptz,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "profiles_select_own" on public.profiles
  for select using (
    auth.uid() = id
    or exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin')
  );

create policy "profiles_update_own" on public.profiles
  for update using (auth.uid() = id);

-- No INSERT/DELETE policy for regular clients: rows are created only by the
-- trigger below (service-level, bypasses RLS via SECURITY DEFINER) and
-- deleted only via the auth.users cascade. This is deliberate, not an
-- oversight — enforces FR-002's "no partial account on denied consent."

comment on table public.profiles is
  'Traveller profile, 1:1 extension of auth.users. Row is created exclusively by the handle_new_user trigger, never by direct client insert.';

-- ---------------------------------------------------------------------------
-- H1 resolution: real trigger-based profile provisioning.
-- ---------------------------------------------------------------------------
create function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id)
  values (new.id)
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- interests / profile_interests
-- ---------------------------------------------------------------------------
create table public.interests (
  id     smallint primary key generated always as identity,
  slug   text unique not null,
  label  text not null
);

comment on table public.interests is
  'Curated onboarding interest tags (reference/lookup data, not user data) — seeded below.';

create table public.profile_interests (
  profile_id   uuid not null references public.profiles(id) on delete cascade,
  interest_id  smallint not null references public.interests(id) on delete cascade,  -- fixes M2
  weight       numeric not null default 1.0,
  source       text not null default 'onboarding' check (source in ('onboarding', 'inferred', 'explicit_feedback')),
  updated_at   timestamptz not null default now(),
  primary key (profile_id, interest_id)
);

alter table public.profile_interests enable row level security;

create policy "profile_interests_own" on public.profile_interests
  for all using (auth.uid() = profile_id)
  with check (auth.uid() = profile_id);

-- Reference-data seed (NOT fake user/application data — a curated lookup
-- table analogous to a category enum, required for onboarding to function).
insert into public.interests (slug, label) values
  ('heritage',          'Heritage & History'),
  ('food',               'Food & Cuisine'),
  ('nature',             'Nature & Outdoors'),
  ('nightlife',          'Nightlife'),
  ('adventure',          'Adventure & Sports'),
  ('shopping',           'Shopping & Markets'),
  ('art_culture',        'Art & Culture'),
  ('relaxation',         'Relaxation & Wellness'),
  ('photography',        'Photography'),
  ('local_experiences',  'Local Experiences'),
  ('spiritual',          'Spiritual & Pilgrimage'),
  ('family_friendly',    'Family Friendly')
on conflict (slug) do nothing;
