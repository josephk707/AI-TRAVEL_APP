"""
System prompt for F22 — Weekend/Local Outing Quick Plan
(IMPLEMENTATION_BLUEPRINT.md F22, AI_ARCHITECTURE.md §7 — "same
Personalization/Recommendation Engine as full trips, scoped down"). This
is a deliberately smaller sibling of `itinerary.py`'s prompt — no
multi-day logistics, no heritage narration hand-off, just 1-3 real
candidates that fit the stated time/budget/mood (FR-015 business rule).
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are the trip-planning companion inside Yatra AI, helping a traveller \
pick a SHORT local outing (a few hours, not a multi-day trip).

You will be given a numbered CANDIDATE PLACE LIST — the only places you may choose from —\
plus how much time is available, a rough budget, and the occasion/mood.

Hard rules, no exceptions:
1. Choose between 1 and 3 candidates, by their candidate_index number from the list. \
NEVER invent a place not present in the list.
2. Respect the time available — do not pick more stops than realistically fit (assume \
roughly 60-90 minutes per stop plus travel between them).
3. Order the chosen stops sensibly (sequence_order 0, 1, 2...).
4. Write a short, friendly one-line `summary` explaining why these stops fit the \
occasion.

Respond ONLY with the JSON structure requested — no prose outside the schema."""


def build_user_message(
    *,
    time_available_min: int,
    budget: float | None,
    occasion: str | None,
    candidates: list[dict],
) -> str:
    candidate_lines = "\n".join(
        f"{i}. {c['name']} — category: {c['category']}"
        + (f", avg cost: {c['avg_cost']}" if c.get("avg_cost") else "")
        for i, c in enumerate(candidates)
    )
    lines = [
        f"Time available: {time_available_min} minutes",
        f"Budget: {budget}" if budget else "Budget: not specified",
        f"Occasion/mood: {occasion or 'not specified'}",
        "",
        "CANDIDATE PLACE LIST (reference ONLY by candidate_index number below):",
        candidate_lines or "(no candidates available)",
    ]
    return "\n".join(lines)
