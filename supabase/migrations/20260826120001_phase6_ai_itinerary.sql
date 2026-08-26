-- Phase 6 — F3 Itinerary Generation: adds the weather-flagging columns
-- ARCHITECTURE_REVIEW.md H7 identified as missing from the pipeline's
-- validation steps (PRD §16 "outdoor activities affected by adverse
-- forecast weather are flagged with a suggested indoor or alternative
-- option"). No existing column could carry this without overloading
-- `verify_on_arrival` (which DATABASE_SCHEMA.md documents specifically as
-- "opening hours unknown", a different, unrelated condition) — a new,
-- explicit column pair is the correct fix, not a workaround crammed into
-- `notes`.

alter table public.itinerary_items
  add column weather_flag boolean not null default false,
  add column weather_alternative_suggestion text;

comment on column public.itinerary_items.weather_flag is
  'Set by the F3 business-rule validator (AI_ARCHITECTURE.md §2 step 4, H7 fix) when this item is scheduled outdoors on a date/location with an adverse forecast. Never set by the LLM directly — computed deterministically from weather_cache.';
comment on column public.itinerary_items.weather_alternative_suggestion is
  'Plain-language suggested indoor/alternative option shown alongside weather_flag, per PRD §16.';
