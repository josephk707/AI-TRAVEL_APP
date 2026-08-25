-- feedback_signals, personalization_profile, ai_conversations, ai_messages —
-- DATABASE_SCHEMA.md §10.
--
-- SCHEMA FIX APPLIED:
--   M8 (MEDIUM): ai_messages.conversation_id is now NULLABLE, with a new
--   `context_type` discriminator ('chat' | 'photo_qa') and a check
--   constraint requiring conversation_id when context_type = 'chat'.
--   AI_ARCHITECTURE.md §6 (Visual Q&A) logs a response per single-shot photo
--   question — not part of an ongoing chat thread — but the original schema
--   made conversation_id NOT NULL, which would have forced either a
--   throwaway conversation row per photo question or a constraint violation.
--   This is a genuine conflict between DATABASE_SCHEMA.md and
--   AI_ARCHITECTURE.md, resolved here in the database layer per this
--   phase's explicit instruction to identify and document such conflicts.
--   No AI functionality is implemented by this fix — schema only.

create table public.feedback_signals (
  id                   uuid primary key default gen_random_uuid(),
  user_id              uuid not null references public.profiles(id) on delete cascade,
  trip_id              uuid references public.trips(id) on delete cascade,
  itinerary_item_id    uuid references public.itinerary_items(id) on delete set null,
  signal_type          text not null
                         check (signal_type in ('accept', 'reject', 'thumbs_up', 'thumbs_down', 'explicit_correction', 'review_submitted')),
  value                jsonb not null default '{}',
  created_at           timestamptz not null default now()
);

create index feedback_signals_user_idx on public.feedback_signals (user_id, created_at desc);

alter table public.feedback_signals enable row level security;

create policy "feedback_signals_own" on public.feedback_signals
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create table public.personalization_profile (
  user_id              uuid primary key references public.profiles(id) on delete cascade,
  preference_weights   jsonb not null default '{}',
  taste_embedding      vector(1536),
  updated_at           timestamptz not null default now()
);

alter table public.personalization_profile enable row level security;

create policy "personalization_profile_own_select" on public.personalization_profile
  for select using (auth.uid() = user_id);

-- Deliberately no INSERT/UPDATE policy for regular clients: this table is
-- computed and written server-side only, by the Personalization Engine
-- using the service-role key (AI_ARCHITECTURE.md §7).

-- ---------------------------------------------------------------------------
create table public.ai_conversations (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references public.profiles(id) on delete cascade,
  trip_id      uuid references public.trips(id) on delete cascade,
  started_at   timestamptz not null default now()
);

create table public.ai_messages (
  id                uuid primary key default gen_random_uuid(),
  conversation_id   uuid references public.ai_conversations(id) on delete cascade,  -- fixes M8: now nullable
  context_type      text not null default 'chat' check (context_type in ('chat', 'photo_qa')),
  role              text not null check (role in ('user', 'assistant', 'system')),
  content           text not null,
  model             text,
  tokens_used       integer,
  confidence        text check (confidence in ('high', 'low')),
  created_at        timestamptz not null default now(),
  check (context_type <> 'chat' or conversation_id is not null)
);

create index ai_messages_conversation_idx on public.ai_messages (conversation_id, created_at);

alter table public.ai_conversations enable row level security;
alter table public.ai_messages enable row level security;

create policy "ai_conversations_own" on public.ai_conversations
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "ai_messages_own" on public.ai_messages
  for all using (
    conversation_id is not null
    and exists (select 1 from public.ai_conversations c where c.id = conversation_id and c.user_id = auth.uid())
  );

comment on column public.ai_messages.context_type is
  'chat = part of an ai_conversations thread (conversation_id required). photo_qa = standalone Visual Q&A response (AI_ARCHITECTURE.md §6), conversation_id may be null. Fixes ARCHITECTURE_REVIEW.md M8.';

comment on policy "ai_messages_own" on public.ai_messages is
  'Deliberately grants no client access to photo_qa rows (conversation_id is null there) — Visual Q&A answers are returned synchronously in the API response and logged only for backend audit/golden-set purposes (AI_ARCHITECTURE.md §6 step 5), read via the service-role key. No product screen reads ai_messages directly for photo_qa history; add a user_id column here if that ever changes.';
