-- UI/Language phase — adds a real, persisted UI-language preference to
-- profiles (DATABASE_SCHEMA.md §3). Reuses the existing profiles table
-- rather than creating a new one, per this phase's explicit instruction
-- to prefer the existing schema wherever possible.
--
-- Six languages: the union of what F10 (dynamic text translation) and F10's
-- phrasebook seed already support in this codebase (Hindi, Telugu,
-- Malayalam, Kannada, Tamil) plus English as the default — not a new
-- product decision, just aligning the UI-language set with what the app
-- already translates into elsewhere.

alter table public.profiles
  add column preferred_language text not null default 'en'
    check (preferred_language in ('en', 'hi', 'te', 'ml', 'kn', 'ta'));

comment on column public.profiles.preferred_language is
  'UI display language + AI-generated-content language preference (ISO 639-1). Default en.';
