-- Final Personalization phase — two small, nullable additions to the
-- EXISTING profiles table (reused, not duplicated), matching the exact
-- pattern already used for travel_style/pace/budget_bracket: a direct
-- onboarding-answer column, no new table. `personalization_profile`
-- (already existing since migration 20260825120008, previously unused)
-- is reused as-is for the COMPUTED "Travel DNA" output — see
-- app/repositories/personalization_repository.py.

alter table public.profiles
  add column travel_companion text
    check (travel_companion in ('solo', 'family', 'friends', 'couple', 'flexible')),
  add column trip_motivation text check (char_length(trip_motivation) <= 500);

comment on column public.profiles.travel_companion is
  'Who the traveller usually travels with — onboarding input, Final Personalization phase.';
comment on column public.profiles.trip_motivation is
  'Free-text answer to "What makes a trip special for you?" — onboarding input, Final Personalization phase. Real user-provided context for the AI, never fabricated.';
