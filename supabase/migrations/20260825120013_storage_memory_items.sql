-- Supabase Storage foundation for Memory Box (this phase's §7) — bucket +
-- RLS policies only. The Memory Box FEATURE (upload UI, download flow) is
-- explicitly NOT implemented this phase; this is the storage-layer
-- counterpart to the memory_items table (migration 20260825120005).
--
-- Path convention: memory-items/{trip_id}/{user_id}/{uuid}-{original_filename}
--   - trip_id first: matches the table's dominant "everything for this
--     trip" access pattern and lets a whole trip's files be listed/removed
--     as one prefix.
--   - user_id second: identifies the uploader directly from the path, so
--     storage-level RLS can enforce the SAME author-or-trip-owner rule
--     applied to the memory_items table itself (fixes the same class of
--     issue as H6 — if the DB row were delete-restricted to the author but
--     the underlying file object were not, a co-member could still destroy
--     the file directly via the Storage API, defeating the point of the
--     H6 fix). Consistency between table RLS and storage RLS is
--     deliberate, not incidental.
--
-- Content constraints (Proposed Target — PRD does not specify exact
-- numbers; documented here explicitly per this phase's instructions
-- rather than left implicit): 25MB per file, common phone photo/video
-- formats only.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'memory-items',
  'memory-items',
  false,  -- private bucket; all access mediated by RLS below (or the backend's signed-URL flow)
  26214400,  -- 25 MB
  array['image/jpeg', 'image/png', 'image/heic', 'image/webp', 'video/mp4', 'video/quicktime']
)
on conflict (id) do nothing;

-- Shared viewing: any trip member can list/read files under a trip's folder.
create policy "memory_items_storage_select_member" on storage.objects
  for select using (
    bucket_id = 'memory-items'
    and public.is_trip_member(((storage.foldername(name))[1])::uuid)
  );

-- Upload: any trip member, but only into their own user_id sub-folder.
create policy "memory_items_storage_insert_own" on storage.objects
  for insert with check (
    bucket_id = 'memory-items'
    and public.is_trip_member(((storage.foldername(name))[1])::uuid)
    and ((storage.foldername(name))[2]) = auth.uid()::text
  );

-- Mutation restricted to the uploader (their own sub-folder) or the trip
-- owner — mirrors memory_items_update/delete_author_or_owner exactly.
create policy "memory_items_storage_update_author_or_owner" on storage.objects
  for update using (
    bucket_id = 'memory-items'
    and (
      ((storage.foldername(name))[2]) = auth.uid()::text
      or exists (
        select 1 from public.trips t
        where t.id = ((storage.foldername(name))[1])::uuid
          and t.owner_id = auth.uid()
      )
    )
  );

create policy "memory_items_storage_delete_author_or_owner" on storage.objects
  for delete using (
    bucket_id = 'memory-items'
    and (
      ((storage.foldername(name))[2]) = auth.uid()::text
      or exists (
        select 1 from public.trips t
        where t.id = ((storage.foldername(name))[1])::uuid
          and t.owner_id = auth.uid()
      )
    )
  );
