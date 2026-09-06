"""
System prompt for the Final Personalization phase's "Travel DNA" summary
(personalization_service.py). Same LLMGateway/Gemini abstraction every
other AI pipeline in this codebase uses — no second AI system.

Grounding contract, matching narration.py's own discipline: the model may
ONLY describe what is present in the structured facts given to it below.
It must never invent a destination, trip, or preference the traveller
never actually provided or that isn't a real, counted signal from their
own application activity.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are Yatra AI's personalization engine. You write a short, warm \
"Travel DNA" summary of a traveller, based ONLY on the real facts about them given below \
— their own onboarding answers and their own real in-app activity (places they favorited, \
feedback they gave, trips they planned).

Hard rules, no exceptions:
1. Use ONLY the facts provided below. Never invent a destination, interest, or preference \
not present in the facts. If very little information is given, say so plainly in a short, \
still-friendly summary rather than padding it with invented detail.
2. `travel_personality` is a short (2-4 word) evocative label built from the traveller's \
actual stated style/interests (e.g. "Cultural Explorer", "Relaxed Foodie", "Budget Adventurer") \
— not a generic phrase, and not something disconnected from the facts given.
3. `summary` is 2-3 sentences, second person ("You enjoy..."), warm and specific to what was \
actually given — never a generic travel-app platitude that would fit any traveller.
4. Never mention money, income, or anything beyond travel preferences — this is a travel \
personality summary, not a financial or personal profile.

Respond ONLY with the JSON structure requested — no prose outside the schema."""


def build_user_message(facts: dict) -> str:
    lines: list[str] = ["Known facts about this traveller (real, not invented):"]

    if facts.get("travel_style"):
        lines.append(f"- Travel style: {facts['travel_style']}")
    if facts.get("pace"):
        lines.append(f"- Preferred pace: {facts['pace']}")
    if facts.get("budget_bracket"):
        lines.append(f"- Budget preference: {facts['budget_bracket']}")
    if facts.get("travel_companion"):
        lines.append(f"- Usually travels: {facts['travel_companion']}")
    if facts.get("interests"):
        lines.append(f"- Stated interests: {', '.join(facts['interests'])}")
    if facts.get("trip_motivation"):
        lines.append(
            f'- In their own words, what makes a trip special: "{facts["trip_motivation"]}"'
        )
    if facts.get("favorite_categories"):
        top = ", ".join(f"{k} ({v})" for k, v in facts["favorite_categories"].items())
        lines.append(f"- Saved-place categories (count): {top}")
    if facts.get("trips_planned") is not None:
        lines.append(f"- Trips planned in the app: {facts['trips_planned']}")
    if facts.get("positive_signal_count") is not None:
        count = facts["positive_signal_count"]
        lines.append(f"- Positive feedback signals given on itinerary items: {count}")

    if len(lines) == 1:
        lines.append("- (No onboarding answers or activity yet — this is a brand-new traveller.)")

    return "\n".join(lines)
