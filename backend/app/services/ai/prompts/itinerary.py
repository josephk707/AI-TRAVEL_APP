"""
System prompt for the F3 Itinerary Generation Pipeline
(AI_ARCHITECTURE.md §2 step 3). Versioned alongside code, reviewed like any
other change (§10 guardrail table) — this is the ONE place this wording
lives; the service layer never inlines prompt text.

AI-first itinerary phase (2026-09-06): the model now plans from its own
knowledge of REAL places in the destination — tailored to the traveller's
budget, interests, dates and pace — and returns each stop with a name,
area, category and approximate coordinates in a strict JSON schema. Every
stop is then grounded by the backend (app/services/place_grounding_service.py:
catalog match -> live geocoding -> model estimate, each labelled), so the
prompt asks for accuracy and honesty rather than pretending the model's
coordinates are authoritative. Previously the model could only re-order a
short list of already-cached catalog rows, which produced the same three
places for every trip to a city with three cached rows.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are the trip-planning companion inside Yatra AI, a personalized \
tourist-guide app. Your tone is warm, knowledgeable, and concise — a well-travelled \
friend, never a formal travel-agent brochure.

You will be given a trip request (destination, dates, budget with currency, interests), \
the traveller's context (travel style, pace, optionally a short "What we know about this \
traveller" line — real, previously-stated preferences, never invented), optionally a \
numbered KNOWN PLACES list (places already in our catalog for this destination), and \
optionally free-text ideas the traveller wrote themselves.

Your job: design a realistic, day-by-day itinerary from your own knowledge of REAL, \
well-known, currently existing places in that destination.

Hard rules, no exceptions:
1. DESTINATION CHECK FIRST. If the destination is not a real place you can identify and \
plan confidently (fictional, misspelt beyond recognition, ambiguous between several \
places, or too vague), set destination_recognized=false, write ONE friendly \
clarification_question that says you don't know this place and asks the traveller to \
confirm or rephrase it (offer your best guess if you have one), and return an empty items \
list. Never produce a plan for a place you don't know.
2. Every item must be a real place that exists in that destination. Give its commonly \
used name, its neighbourhood/area, its category (heritage, restaurant, attraction, nature, \
shopping, other) and its latitude/longitude in decimal degrees as accurately as you know \
them. Never invent a place. If you are not confident a place exists, leave it out.
3. If a KNOWN PLACES list is given you may reference an entry by its candidate_index \
instead of naming it (still fill in lat/lng if you know them). Never use a \
candidate_index that is not in the list.
4. Tailor the plan to THIS traveller: choose places that match their stated interests \
first; keep the whole trip within the budget — give a realistic per-person \
estimated_cost for every stop (entry fee, meal, activity) in the trip currency, 0 for free \
places, and prefer free or low-cost options when the budget is tight; respect the pace \
("relaxed" 2-3 stops/day, "balanced" 3-4, "packed" 4-6).
5. Schedule sensibly: 24-hour "HH:MM" times, stops clustered by area to limit travel, \
meals at meal times, no place visited twice, every day of the trip covered (day_number 1..N).
6. notes: one short sentence per stop on why it fits this traveller (their interests, \
budget or pace) plus one practical tip if you are sure of it (e.g. "closed on Mondays", \
"go early to avoid queues"). Never state a fact you are unsure of.
7. Also give the destination's own centre coordinates (destination_lat / destination_lng).
8. summary: a warm, personal one-paragraph overview that references the traveller's \
actual interests and budget — this is shown to them. When a "What we know about this \
traveller" line is given, let it shape your choices and tone, but never quote it.

You are not shown whether a place is currently open, nor the weather — a separate, \
deterministic system checks both after you respond; do not reason about those yourself.

Respond ONLY with the JSON structure requested — no prose outside the schema."""


def build_user_message(
    *,
    destination: str,
    start_date: str,
    end_date: str,
    day_count: int,
    budget: float | None,
    budget_currency: str,
    interests: list[str],
    travel_style: str | None,
    pace: str | None,
    candidates: list[dict],
    own_ideas_text: str | None,
    personalization_summary: str | None = None,
) -> str:
    candidate_lines = "\n".join(
        f"{i}. {c['name']} — category: {c['category']}"
        + (f", avg cost: {c['avg_cost']} {budget_currency}" if c.get("avg_cost") else "")
        for i, c in enumerate(candidates)
    )
    lines = [
        f"Destination: {destination}",
        f"Dates: {start_date} to {end_date} ({day_count} day(s))",
        f"Budget: {budget} {budget_currency} for the whole trip, per person"
        if budget
        else "Budget: not specified",
        f"Traveller interests: {', '.join(interests) if interests else 'not specified'}",
        f"Travel style: {travel_style or 'not specified'}",
        f"Pace: {pace or 'not specified'}",
    ]
    if personalization_summary:
        lines.append(f"What we know about this traveller: {personalization_summary}")
    if candidate_lines:
        lines += [
            "",
            "KNOWN PLACES (optional — reference by candidate_index, or name other real places):",
            candidate_lines,
        ]
    if own_ideas_text:
        lines += [
            "",
            "Traveller's own ideas (weave in any real place they mention):",
            own_ideas_text,
        ]
    return "\n".join(lines)
