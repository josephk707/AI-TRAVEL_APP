"""
F15 — Budget Estimate, planning-time tracking (IMPLEMENTATION_BLUEPRINT.md
F15, API_SPECIFICATION.md §14). Over-budget is ALWAYS advisory — logging an
expense never blocks or auto-cancels anything (FR-016 business rule,
matching the same reading already applied to F3's business-rule validator,
`business_rules.py`'s own module docstring).
"""

from __future__ import annotations

from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.repositories.budget_repository import BudgetRepository
from app.repositories.group_repository import GroupRepository
from app.repositories.trips_repository import TripsRepository
from app.services import notification_service

_TOLERANCE_PCT = 10.0


def _compute_per_member_owed(expenses: list[dict]) -> dict[str, float]:
    """F23 — split-calculation. Each expense's `amount * share` is
    allocated to the named user_id, summed across every expense that
    carries a split_with breakdown (expenses without one are entirely the
    logging member's own, per F15's original single-payer model)."""
    owed: dict[str, float] = {}
    for expense in expenses:
        for entry in expense.get("split_with") or []:
            owed[entry["user_id"]] = owed.get(entry["user_id"], 0.0) + float(
                expense["amount"]
            ) * float(entry["share"])
    return {uid: round(amount, 2) for uid, amount in owed.items()}


async def get_budget_summary(trip_id: str, user_id: str) -> dict:
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")

    budget_repo = BudgetRepository()
    expenses = await budget_repo.list_expenses(trip_id)
    total_spent = await budget_repo.total_spent(trip_id)
    planned = float(trip["budget_planned"]) if trip["budget_planned"] else None
    over_budget = planned is not None and total_spent > planned * (1 + _TOLERANCE_PCT / 100)

    return {
        "trip_id": trip_id,
        "planned_budget": planned,
        "total_spent": total_spent,
        "over_budget": over_budget,
        "expenses": expenses,
        "per_member_owed": _compute_per_member_owed(expenses),
    }


async def log_expense(
    trip_id: str,
    user_id: str,
    category: str,
    amount: float,
    currency: str,
    split_with: list[dict] | None = None,
) -> tuple[dict, bool]:
    """Returns (expense_row, over_budget)."""
    trips_repo = TripsRepository()
    trip = await trips_repo.get_trip(trip_id)
    if trip is None:
        raise NotFoundError("This trip could not be found.")
    if not await trips_repo.is_trip_accessible(trip_id, user_id):
        raise ForbiddenError("You do not have access to this trip.")

    if split_with:
        group_repo = GroupRepository()
        for entry in split_with:
            split_user_id = entry["user_id"]
            is_owner = split_user_id == str(trip["owner_id"])
            if not is_owner and not await group_repo.is_member(trip_id, split_user_id):
                raise AppError(
                    "SPLIT_WITH_NON_MEMBER",
                    "An expense can only be split with members of this trip.",
                    422,
                )

    budget_repo = BudgetRepository()
    expense = await budget_repo.create_expense(
        trip_id, user_id, category, amount, currency, split_with
    )

    total_spent = await budget_repo.total_spent(trip_id)
    planned = float(trip["budget_planned"]) if trip["budget_planned"] else None
    over_budget = planned is not None and total_spent > planned * (1 + _TOLERANCE_PCT / 100)

    if over_budget:
        await notification_service.dispatch(
            trip["owner_id"] if isinstance(trip["owner_id"], str) else str(trip["owner_id"]),
            type_="system",
            title="Budget update",
            body=f"Your trip '{trip['title']}' is now over its planned budget.",
            trip_id=trip_id,
            payload={"total_spent": total_spent, "planned_budget": planned},
        )

    return expense, over_budget
