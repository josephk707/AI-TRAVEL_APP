-- Fix: `interests` was created in migration 20260825120002 without RLS
-- enabled at all — a genuine oversight, found by the live verification
-- suite (tests/test_live_database.py) after applying migrations to a real
-- Supabase project, not by inspecting the migration source.
--
-- interests is non-sensitive, curated reference/lookup data (see
-- migration 20260825120002's own comment) that every authenticated user
-- needs to read for onboarding — the fix is a public-read policy, matching
-- the exact pattern already used for `pois` and `phrasebook_entries`, not
-- a client-write policy (writes stay admin/service-role only, consistent
-- with every other lookup table in this schema).

alter table public.interests enable row level security;

create policy "interests_read_all" on public.interests
  for select using (auth.role() = 'authenticated');
