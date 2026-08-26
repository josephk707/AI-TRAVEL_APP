"""
Deterministic business-rule validation for the Itinerary Generation
(F3) and Conversational Modification (F5) pipelines — AI_ARCHITECTURE.md
§2 step 4 / §4 step 3. Explicitly NOT delegated to the LLM: every check
here runs on plain data the pipeline already has, so "is this itinerary
allowed" never depends on asking a model to grade its own work.

Five checks, matching AI_ARCHITECTURE.md §2 step 4 plus the H7 fix
(ARCHITECTURE_REVIEW.md — the weather rule was documented as missing and
is added here as the fifth, not folded into an existing one):
  1. total cost vs budget (>10% tolerance → flagged, PRD §16)
  2. opening-hours conflicts → verify_on_arrival when hours unknown
  3. travel-time buffers between geographically distant stops
  4. itinerary items must not overlap
  5. outdoor items checked against weather_cache forecast (H7)

Budget is ALWAYS a soft flag, never a hard rejection — F15's own business
rule states budget tracking "never blocks or auto-cancels a plan item"
(API_SPECIFICATION.md §14), and this is read here as applying to the
itinerary as a whole, not just post-trip expense tracking. Travel-time and
overlap conflicts ARE hard-rejectable for F5 (a user-requested change that
would create one is refused with the conflict + closest alternative,
AI_ARCHITECTURE.md §4 step 4) but only flagged (never silently dropped)
during F3 generation, since generation's own failure mode is the curated
fallback template, not a partial/blocked plan.
"""

from __future__ import annotations

import math
from datetime import date as date_cls
from typing import Any, TypedDict

from app.services import weather_service

BUDGET_TOLERANCE_PCT = 10.0
LONG_DISTANCE_KM = 50.0
MIN_TRAVEL_BUFFER_MIN = 60
OUTDOOR_CATEGORIES = {"nature", "attraction", "heritage"}
_EARTH_RADIUS_KM = 6371.0


class BudgetSummary(TypedDict):
    estimated_total: float
    planned_budget: float | None
    over_budget: bool
    tolerance_pct: float


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _parse_hm(value: str | None) -> int | None:
    """Returns minutes-since-midnight, or None if unparseable/absent."""
    if not value:
        return None
    try:
        hh, mm = value.split(":")
        return int(hh) * 60 + int(mm)
    except (ValueError, AttributeError):
        return None


def compute_budget_summary(
    items: list[dict[str, Any]], planned_budget: float | None
) -> BudgetSummary:
    total = sum(float(item.get("estimated_cost") or 0) for item in items)
    over_budget = planned_budget is not None and total > planned_budget * (
        1 + BUDGET_TOLERANCE_PCT / 100
    )
    return BudgetSummary(
        estimated_total=round(total, 2),
        planned_budget=planned_budget,
        over_budget=over_budget,
        tolerance_pct=BUDGET_TOLERANCE_PCT,
    )


def check_travel_time_conflicts(items_by_day: dict[int, list[dict[str, Any]]]) -> list[str]:
    """Items within one day, already ordered by sequence_order. Flags a gap
    that's too short between geographically distant consecutive stops.
    Never mutates — the caller decides what, if anything, to do about a
    flagged conflict (soft note for F3, hard rejection for F5)."""
    conflicts: list[str] = []
    for day_number, items in items_by_day.items():
        for prev, nxt in zip(items, items[1:], strict=False):
            if prev.get("poi_lat") is None or nxt.get("poi_lat") is None:
                continue
            distance = haversine_km(
                prev["poi_lat"], prev["poi_lng"], nxt["poi_lat"], nxt["poi_lng"]
            )
            if distance < LONG_DISTANCE_KM:
                continue
            prev_end = _parse_hm(prev.get("planned_end"))
            next_start = _parse_hm(nxt.get("planned_start"))
            if prev_end is None or next_start is None:
                continue
            gap = next_start - prev_end
            if gap < MIN_TRAVEL_BUFFER_MIN:
                prev_name = prev.get("poi_name", "a stop")
                next_name = nxt.get("poi_name", "the next stop")
                conflicts.append(
                    f"Day {day_number}: only {max(gap, 0)} min between "
                    f"'{prev_name}' and '{next_name}', "
                    f"which are {distance:.0f} km apart — consider more travel buffer."
                )
    return conflicts


def check_item_overlaps(items_by_day: dict[int, list[dict[str, Any]]]) -> list[str]:
    conflicts: list[str] = []
    for day_number, items in items_by_day.items():
        for prev, nxt in zip(items, items[1:], strict=False):
            prev_end = _parse_hm(prev.get("planned_end"))
            next_start = _parse_hm(nxt.get("planned_start"))
            if prev_end is not None and next_start is not None and next_start < prev_end:
                conflicts.append(
                    f"Day {day_number}: '{nxt.get('poi_name', 'an item')}' starts before "
                    f"'{prev.get('poi_name', 'the previous item')}' ends."
                )
    return conflicts


def apply_opening_hours_check(item: dict[str, Any]) -> bool:
    """Returns verify_on_arrival. Per DATABASE_SCHEMA.md, `pois.opening_hours`
    is unstructured jsonb sourced either from curated seed data or Google
    Places' own raw (and considerably more complex) `regularOpeningHours`
    shape — no single documented schema exists to parse precise hour
    ranges reliably. Documented decision (CLAUDE.md §13): this check
    verifies PRESENCE of opening-hours data (matching DATABASE_SCHEMA.md's
    own "null => verify on arrival" contract exactly) rather than
    attempting fine-grained hour-range conflict detection against an
    unspecified format — a real, bounded limitation, not a shortcut taken
    silently. See docs/PHASE_STATUS.md Phase 6 Known Limitations."""
    return item.get("poi_opening_hours") is None


async def apply_weather_flags(
    items_by_day: dict[int, list[dict[str, Any]]], day_dates: dict[int, date_cls | None]
) -> None:
    """Mutates each outdoor-category item in place, setting `weather_flag`/
    `weather_alternative_suggestion` (H7 fix). No-op (never raises) when
    weather isn't configured or the date falls outside the forecast
    horizon — `weather_service.check_adverse_weather` already returns None
    for "unknown", which this treats as "do not flag" (never guess)."""
    for day_number, items in items_by_day.items():
        day_date = day_dates.get(day_number)
        if day_date is None:
            continue
        for item in items:
            if item.get("poi_category") not in OUTDOOR_CATEGORIES:
                continue
            if item.get("poi_lat") is None:
                continue
            adverse = await weather_service.check_adverse_weather(
                item["poi_lat"], item["poi_lng"], day_date.isoformat()
            )
            if adverse:
                item["weather_flag"] = True
                item["weather_alternative_suggestion"] = (
                    f"Adverse weather is forecast for {day_date.isoformat()} — consider an "
                    "indoor alternative (a museum, covered market, or heritage interior nearby) "
                    "for this stop."
                )


def compute_planned_end(planned_start: str | None, duration_min: int | None) -> str | None:
    minutes = _parse_hm(planned_start)
    if minutes is None or duration_min is None:
        return None
    total = (minutes + duration_min) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def group_by_day(
    items: list[dict[str, Any]], day_number_key: str = "day_number"
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(item[day_number_key], []).append(item)
    for day_items in grouped.values():
        day_items.sort(key=lambda i: i.get("sequence_order", 0))
    return grouped


async def validate_itinerary(
    items: list[dict[str, Any]], day_dates: dict[int, date_cls | None], planned_budget: float | None
) -> tuple[BudgetSummary, list[str]]:
    """The single entry point both F3 and F5 call. Returns
    (budget_summary, conflicts) — conflicts is advisory prose for F3,
    and F5's caller decides whether any conflict is severe enough to
    reject the specific requested diff outright."""
    for item in items:
        item["verify_on_arrival"] = apply_opening_hours_check(item)
        item.setdefault("weather_flag", False)
        item.setdefault("weather_alternative_suggestion", None)

    by_day = group_by_day(items)
    await apply_weather_flags(by_day, day_dates)

    conflicts = check_item_overlaps(by_day) + check_travel_time_conflicts(by_day)
    budget_summary = compute_budget_summary(items, planned_budget)
    return budget_summary, conflicts
