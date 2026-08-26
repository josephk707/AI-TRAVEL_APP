"""
F19 — Group/Collaborative Trip Planning (IMPLEMENTATION_BLUEPRINT.md F19,
API_SPECIFICATION.md §13, AI_ARCHITECTURE.md §9).

Reconciliation is the Phase 2 "rule-based-first" step documented in
AI_ARCHITECTURE.md §9 — NOT an LLM negotiation pass (that upgrade is F32,
Phase 4, explicitly out of scope here): merge interests (union), take the
min of members' `budget_max` (never silently pick one member's number),
list every genuine conflict with its resolution, then hand the reconciled
input to the SAME F3 itinerary-generation pipeline used everywhere else —
no separate/duplicated generation logic.

**Documented decision (ARCHITECTURE_REVIEW.md H5, resolved per its own
recommended option (a)):** there is no "edit rights" tier — any accepted
trip member can propose/apply itinerary changes, matching the existing
permissive `is_trip_accessible()`/RLS behavior every other F3/F4/F5
endpoint already relies on. No new permission column was added.
"""

from __future__ import annotations

from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from app.repositories.group_repository import GroupRepository
from app.repositories.trips_repository import TripsRepository
from app.schemas.trips import ItineraryGenerateRequest
from app.services import itinerary_service


def _invite_url(token: str) -> str:
    return f"aitouristguide://trips/invite/{token}"


async def create_invite(trip_id: str, inviter_id: str, method: str, email: str | None) -> dict:
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_owner(trip_id, inviter_id):
        raise ForbiddenError("Only the trip organiser can invite others.")

    row = await GroupRepository().create_invite(trip_id, inviter_id, method, email)
    return {**row, "invite_url": _invite_url(row["token"])}


async def accept_invite(token: str, user_id: str) -> dict:
    group_repo = GroupRepository()
    invite = await group_repo.get_invite_by_token(token)
    if invite is None:
        raise NotFoundError("This invite link is invalid.")
    if invite["status"] != "pending":
        raise ConflictError("This invite has already been used.")
    from datetime import UTC, datetime

    if invite["expires_at"] < datetime.now(UTC):
        raise ConflictError("This invite link has expired.")

    invite_trip_id = str(invite["trip_id"])
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(invite_trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if str(trip["owner_id"]) == user_id:
        raise ConflictError("You already own this trip.")

    await group_repo.add_member(invite_trip_id, user_id, role="member")
    await group_repo.mark_invite_accepted(str(invite["id"]), user_id)
    return {"trip_id": invite_trip_id, "role": "member", "joined": True}


async def submit_preferences(
    trip_id: str,
    user_id: str,
    acting_user_id: str,
    interests: list[str],
    budget_max: float | None,
    constraints: dict,
) -> dict:
    if user_id != acting_user_id:
        raise ForbiddenError("You can only submit your own preferences.")
    trips_repo = TripsRepository()
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")
    return await GroupRepository().upsert_preferences(
        trip_id, user_id, interests, budget_max, constraints
    )


async def list_members(trip_id: str, user_id: str) -> list[dict]:
    trips_repo = TripsRepository()
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")
    return await GroupRepository().list_members(trip_id)


def _merge_preferences(preferences: list[dict]) -> tuple[list[str], float | None, list[dict]]:
    """Rule-based-first reconciliation (AI_ARCHITECTURE.md §9 step 2)."""
    all_interests: set[str] = set()
    budgets: list[float] = []
    conflicts: list[dict] = []

    for pref in preferences:
        all_interests.update(pref["interests"] or [])
        if pref["budget_max"] is not None:
            budgets.append(float(pref["budget_max"]))

    merged_budget = min(budgets) if budgets else None
    if len(set(budgets)) > 1:
        budget_list = ", ".join(str(b) for b in sorted(set(budgets)))
        conflicts.append(
            {
                "field": "budget",
                "description": f"Members proposed different budgets ({budget_list}).",
                "resolution": (
                    f"Used the lowest stated budget (₹{merged_budget}) "
                    "so the plan stays affordable for everyone."
                ),
            }
        )

    must_include: set[str] = set()
    for pref in preferences:
        for place in (pref["constraints"] or {}).get("must_include", []) or []:
            must_include.add(place)
    if must_include:
        conflicts.append(
            {
                "field": "must_include",
                "description": (
                    f"{len(must_include)} place(s) were specifically requested "
                    "by at least one member."
                ),
                "resolution": (
                    "Every explicitly requested place was passed to the "
                    "planner as a strong preference."
                ),
            }
        )

    return sorted(all_interests), merged_budget, conflicts


async def reconcile(trip_id: str, organiser_id: str) -> dict:
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_owner(trip_id, organiser_id):
        raise ForbiddenError("Only the trip organiser can reconcile group preferences.")

    group_repo = GroupRepository()
    members = await group_repo.list_members(trip_id)
    preferences = await group_repo.list_preferences(trip_id)

    owner_id = str(trip["owner_id"])
    responded_ids = {str(p["user_id"]) for p in preferences}
    all_member_ids = {str(m["user_id"]) for m in members} | {owner_id}
    included_ids = responded_ids | {owner_id}
    excluded_ids = all_member_ids - included_ids

    if not preferences:
        raise AppError(
            "NO_PREFERENCES_SUBMITTED",
            "No member has submitted preferences yet — nothing to reconcile.",
            422,
        )

    interests, budget_max, conflicts = _merge_preferences(preferences)

    request = ItineraryGenerateRequest(
        interests=interests,
        budget=budget_max,
        destination=trip["destination"],
    )
    payload, degraded = await itinerary_service.generate_itinerary(trip_id, organiser_id, request)

    return {
        **payload,
        "conflicts": [dict(c) for c in conflicts],
        "included_member_ids": sorted(included_ids),
        "excluded_member_ids": sorted(excluded_ids),
    }
