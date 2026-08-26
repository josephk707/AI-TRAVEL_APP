/**
 * Typed calls to /v1/trips/{id}/budget, /expenses — F15, see
 * docs/API_SPECIFICATION.md §14.
 */

import { apiGet, apiPost } from "./client";

export type ExpenseCategory = "lodging" | "food" | "transport" | "activity" | "other";

export interface Expense {
  id: string;
  trip_id: string;
  user_id: string;
  category: ExpenseCategory;
  amount: number;
  currency: string;
  logged_at: string;
}

export interface BudgetSummary {
  trip_id: string;
  planned_budget: number | null;
  total_spent: number;
  over_budget: boolean;
  expenses: Expense[];
}

interface Envelope<T> {
  data: T;
  meta?: { over_budget?: boolean | null } | null;
}

export async function fetchBudgetSummary(tripId: string, signal?: AbortSignal): Promise<BudgetSummary> {
  const envelope = await apiGet<Envelope<BudgetSummary>>(`/v1/trips/${tripId}/budget`, signal);
  return envelope.data;
}

export interface LogExpenseResult {
  expense: Expense;
  overBudget: boolean;
}

export async function logExpense(
  tripId: string,
  category: ExpenseCategory,
  amount: number,
  currency = "INR",
): Promise<LogExpenseResult> {
  const envelope = await apiPost<Envelope<Expense>>(`/v1/trips/${tripId}/expenses`, {
    category,
    amount,
    currency,
  });
  return { expense: envelope.data, overBudget: envelope.meta?.over_budget ?? false };
}
