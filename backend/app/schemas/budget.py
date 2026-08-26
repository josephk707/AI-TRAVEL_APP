"""Request/response schemas for /v1/trips/{id}/budget, /expenses — F15
(API_SPECIFICATION.md §14)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

_EXPENSE_CATEGORIES = ("lodging", "food", "transport", "activity", "other")


class SplitEntry(BaseModel):
    """F23 — Budget Tracking with Group Expense Splitting (extends F15)."""

    user_id: str
    share: float = Field(gt=0, le=1)


class ExpenseCreateRequest(BaseModel):
    category: str = Field(pattern="^(" + "|".join(_EXPENSE_CATEGORIES) + ")$")
    amount: float = Field(gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    split_with: list[SplitEntry] | None = None


class ExpenseResponse(BaseModel):
    id: str
    trip_id: str
    user_id: str
    category: str
    amount: float
    currency: str
    split_with: list[SplitEntry] | None
    logged_at: datetime


class BudgetSummaryResponse(BaseModel):
    trip_id: str
    planned_budget: float | None
    total_spent: float
    over_budget: bool
    expenses: list[ExpenseResponse]
    per_member_owed: dict[str, float] = Field(default_factory=dict)
