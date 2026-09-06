"""
Shared helper so every AI text-generation pipeline (itinerary, chat
modification, quick plan, heritage narration, photo Q&A) can honor the
traveller's `profiles.preferred_language` without each prompt module
duplicating this logic. Appended to a SYSTEM_PROMPT at the call site —
the static prompt constants in ai/prompts/*.py stay unmodified so this is
a one-line addition per service, not a rewrite of five prompt files.

English is the default and needs no instruction (the prompts are already
written in English) — this only activates for a real non-English
preference.
"""

from __future__ import annotations

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "te": "Telugu",
    "ml": "Malayalam",
    "kn": "Kannada",
    "ta": "Tamil",
}


def language_instruction(preferred_language: str | None) -> str:
    if not preferred_language or preferred_language == "en":
        return ""
    name = LANGUAGE_NAMES.get(preferred_language)
    if name is None:
        return ""
    return (
        f"\n\nIMPORTANT: Write your entire response in {name}, including every free-text field "
        f"(summary, reply, narration, notes). Keep proper nouns — place names, brand names — "
        f"recognizable rather than transliterating them awkwardly, but all narrative/explanatory "
        f"text must be in {name}, not English."
    )
