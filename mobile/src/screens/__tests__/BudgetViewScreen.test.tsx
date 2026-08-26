import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { fetchBudgetSummary, logExpense } from "../../api/budget";
import { ApiError } from "../../api/client";
import { BudgetViewScreen } from "../BudgetViewScreen";

jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useRoute: () => ({ params: { tripId: "trip-1" } }),
}));

jest.mock("../../api/budget", () => ({
  fetchBudgetSummary: jest.fn(),
  logExpense: jest.fn(),
}));

const mockFetchBudgetSummary = fetchBudgetSummary as jest.Mock;
const mockLogExpense = logExpense as jest.Mock;

const EMPTY_SUMMARY = {
  trip_id: "trip-1",
  planned_budget: 10000,
  total_spent: 0,
  over_budget: false,
  expenses: [],
};

describe("BudgetViewScreen", () => {
  beforeEach(() => jest.clearAllMocks());

  it("shows the planned budget and an empty expenses state", async () => {
    mockFetchBudgetSummary.mockResolvedValue(EMPTY_SUMMARY);

    await render(<BudgetViewScreen />);

    await waitFor(() => expect(screen.getByTestId("budget-content")).toBeTruthy());
    expect(screen.getByText("₹10000")).toBeTruthy();
    expect(screen.getByTestId("budget-expenses-empty")).toBeTruthy();
  });

  it("shows a typed error state with retry on failure", async () => {
    mockFetchBudgetSummary.mockRejectedValue(new ApiError(500, "Server exploded"));

    await render(<BudgetViewScreen />);

    await waitFor(() => expect(screen.getByTestId("budget-error")).toBeTruthy());
    expect(screen.getByText("Server exploded")).toBeTruthy();
  });

  it("logs an expense and shows the over-budget notice when applicable", async () => {
    mockFetchBudgetSummary.mockResolvedValue(EMPTY_SUMMARY);
    mockLogExpense.mockResolvedValue({
      expense: {
        id: "exp-1",
        trip_id: "trip-1",
        user_id: "user-1",
        category: "food",
        amount: 500,
        currency: "INR",
        logged_at: "2026-01-01T00:00:00Z",
      },
      overBudget: true,
    });

    await render(<BudgetViewScreen />);
    await waitFor(() => expect(screen.getByTestId("budget-content")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("budget-category-food"));
    });
    await act(async () => {
      fireEvent.changeText(screen.getByTestId("budget-amount-input"), "500");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("budget-log-expense-button"));
    });

    await waitFor(() => expect(mockLogExpense).toHaveBeenCalledWith("trip-1", "food", 500));
    expect(screen.getByTestId("budget-over-toast")).toBeTruthy();
  });

  it("renders real logged expenses returned by the backend", async () => {
    mockFetchBudgetSummary.mockResolvedValue({
      ...EMPTY_SUMMARY,
      total_spent: 500,
      expenses: [
        {
          id: "exp-1",
          trip_id: "trip-1",
          user_id: "user-1",
          category: "food",
          amount: 500,
          currency: "INR",
          logged_at: "2026-01-01T00:00:00Z",
        },
      ],
    });

    await render(<BudgetViewScreen />);

    await waitFor(() => expect(screen.getByTestId("expense-exp-1")).toBeTruthy());
    expect(screen.getByText("INR 500")).toBeTruthy();
  });
});
