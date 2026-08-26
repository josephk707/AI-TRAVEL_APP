import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { fetchBudgetSummary, logExpense } from "../../api/budget";
import { ApiError } from "../../api/client";
import { listTripMembers } from "../../api/group";
import { useAuth } from "../../auth/AuthContext";
import { BudgetViewScreen } from "../BudgetViewScreen";

jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useRoute: () => ({ params: { tripId: "trip-1" } }),
}));

jest.mock("../../api/budget", () => ({
  fetchBudgetSummary: jest.fn(),
  logExpense: jest.fn(),
}));

jest.mock("../../api/group", () => ({
  listTripMembers: jest.fn(),
}));

jest.mock("../../auth/AuthContext", () => ({
  useAuth: jest.fn(),
}));

const mockFetchBudgetSummary = fetchBudgetSummary as jest.Mock;
const mockLogExpense = logExpense as jest.Mock;
const mockListTripMembers = listTripMembers as jest.Mock;
const mockUseAuth = useAuth as jest.Mock;

const EMPTY_SUMMARY = {
  trip_id: "trip-1",
  planned_budget: 10000,
  total_spent: 0,
  over_budget: false,
  expenses: [],
  per_member_owed: {},
};

describe("BudgetViewScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockListTripMembers.mockResolvedValue([]);
    mockUseAuth.mockReturnValue({ user: { id: "user-1" } });
  });

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

    await waitFor(() =>
      expect(mockLogExpense).toHaveBeenCalledWith("trip-1", "food", 500, "INR", undefined),
    );
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

  it("shows a split-equally toggle when the trip has other members, and includes split_with when enabled", async () => {
    mockFetchBudgetSummary.mockResolvedValue(EMPTY_SUMMARY);
    mockListTripMembers.mockResolvedValue([
      {
        trip_id: "trip-1",
        user_id: "user-2",
        display_name: "Alex",
        role: "member",
        invite_status: "accepted",
        invited_at: "2026-01-01T00:00:00Z",
        responded_at: "2026-01-01T00:00:00Z",
      },
    ]);
    mockLogExpense.mockResolvedValue({
      expense: {
        id: "exp-2",
        trip_id: "trip-1",
        user_id: "user-1",
        category: "food",
        amount: 600,
        currency: "INR",
        split_with: [
          { user_id: "user-1", share: 0.5 },
          { user_id: "user-2", share: 0.5 },
        ],
        logged_at: "2026-01-01T00:00:00Z",
      },
      overBudget: false,
    });

    await render(<BudgetViewScreen />);
    await waitFor(() => expect(screen.getByTestId("split-equally-row")).toBeTruthy());

    await act(async () => {
      fireEvent(screen.getByTestId("split-equally-switch"), "valueChange", true);
    });
    await act(async () => {
      fireEvent.changeText(screen.getByTestId("budget-amount-input"), "600");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("budget-log-expense-button"));
    });

    await waitFor(() =>
      expect(mockLogExpense).toHaveBeenCalledWith("trip-1", "food", 600, "INR", [
        { user_id: "user-1", share: 0.5 },
        { user_id: "user-2", share: 0.5 },
      ]),
    );
  });

  it("shows the per-member-owed breakdown when the backend returns one", async () => {
    mockFetchBudgetSummary.mockResolvedValue({
      ...EMPTY_SUMMARY,
      per_member_owed: { "user-2": 300 },
    });

    await render(<BudgetViewScreen />);

    await waitFor(() => expect(screen.getByTestId("per-member-owed")).toBeTruthy());
  });
});
