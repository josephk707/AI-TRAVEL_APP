"""/v1/trips/{trip_id}/budget, /expenses — F15 (API_SPECIFICATION.md §14)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.security import AuthenticatedUser
from app.schemas.budget import BudgetSummaryResponse, ExpenseCreateRequest, ExpenseResponse
from app.schemas.common import Envelope, Meta
from app.services import budget_service

router = APIRouter(prefix="/trips/{trip_id}", tags=["budget"])


def _expense_to_response(row: dict) -> dict:
    return dict(row, id=str(row["id"]), trip_id=str(row["trip_id"]), user_id=str(row["user_id"]))


@router.get("/budget", response_model=Envelope[BudgetSummaryResponse])
async def get_budget(
    trip_id: str, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[BudgetSummaryResponse]:
    summary = await budget_service.get_budget_summary(trip_id, user.id)
    summary["expenses"] = [_expense_to_response(e) for e in summary["expenses"]]
    return Envelope(data=BudgetSummaryResponse.model_validate(summary))


@router.post("/expenses", response_model=Envelope[ExpenseResponse], status_code=201)
async def log_expense(
    trip_id: str, body: ExpenseCreateRequest, user: AuthenticatedUser = Depends(get_current_user)
) -> Envelope[ExpenseResponse]:
    expense, over_budget = await budget_service.log_expense(
        trip_id, user.id, body.category, body.amount, body.currency
    )
    meta = Meta(over_budget=over_budget) if over_budget else None
    return Envelope(data=ExpenseResponse.model_validate(_expense_to_response(expense)), meta=meta)
