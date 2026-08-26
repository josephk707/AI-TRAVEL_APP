import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import * as Location from "expo-location";
import React from "react";

import { ApiError } from "../../api/client";
import { createQuickPlan, saveQuickPlanToCollection } from "../../api/quickPlans";
import { QuickPlanScreen } from "../QuickPlanScreen";

jest.mock("../../api/quickPlans", () => ({
  createQuickPlan: jest.fn(),
  saveQuickPlanToCollection: jest.fn(),
}));

jest.mock("expo-location", () => ({
  requestForegroundPermissionsAsync: jest.fn(),
  getCurrentPositionAsync: jest.fn(),
}));

const mockCreateQuickPlan = createQuickPlan as jest.Mock;
const mockSaveQuickPlanToCollection = saveQuickPlanToCollection as jest.Mock;
const mockRequestForeground = Location.requestForegroundPermissionsAsync as jest.Mock;
const mockGetCurrentPosition = Location.getCurrentPositionAsync as jest.Mock;

function makePlan(overrides: Record<string, unknown> = {}) {
  return {
    id: "plan-1",
    user_id: "user-1",
    time_available_min: 120,
    budget: null,
    occasion: null,
    summary: "A relaxed heritage afternoon.",
    generated_at: "2026-01-01T00:00:00Z",
    items: [{ poi_id: "poi-1", poi_name: "Taj Mahal", poi_category: "heritage", sequence_order: 0 }],
    ...overrides,
  };
}

describe("QuickPlanScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRequestForeground.mockResolvedValue({ granted: true });
    mockGetCurrentPosition.mockResolvedValue({ coords: { latitude: 27.17, longitude: 78.04 } });
  });

  it("builds a real quick plan using the device's current location", async () => {
    mockCreateQuickPlan.mockResolvedValue(makePlan());

    await render(<QuickPlanScreen />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("generate-quick-plan-button"));
    });

    await waitFor(() => expect(screen.getByTestId("quick-plan-result")).toBeTruthy());
    expect(screen.getByText("A relaxed heritage afternoon.")).toBeTruthy();
    expect(screen.getByTestId("quick-plan-item-poi-1")).toBeTruthy();
    expect(mockCreateQuickPlan).toHaveBeenCalledWith(120, {
      budget: undefined,
      occasion: undefined,
      lat: 27.17,
      lng: 78.04,
    });
  });

  it("falls back to the home region when location permission is denied", async () => {
    mockRequestForeground.mockResolvedValue({ granted: false });
    mockCreateQuickPlan.mockResolvedValue(makePlan());

    await render(<QuickPlanScreen />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("generate-quick-plan-button"));
    });

    await waitFor(() => expect(screen.getByTestId("quick-plan-result")).toBeTruthy());
    expect(mockCreateQuickPlan).toHaveBeenCalledWith(120, {
      budget: undefined,
      occasion: undefined,
      lat: undefined,
      lng: undefined,
    });
  });

  it("shows a typed error state when there isn't enough local data", async () => {
    mockCreateQuickPlan.mockRejectedValue(
      new ApiError(422, "There isn't enough local data for this area yet.", "NOT_ENOUGH_LOCAL_DATA"),
    );

    await render(<QuickPlanScreen />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("generate-quick-plan-button"));
    });

    await waitFor(() => expect(screen.getByTestId("quick-plan-error")).toBeTruthy());
    expect(screen.getByText("There isn't enough local data for this area yet.")).toBeTruthy();
  });

  it("rejects an invalid time-available value before calling the backend", async () => {
    await render(<QuickPlanScreen />);

    await act(async () => {
      fireEvent.changeText(screen.getByTestId("quick-plan-time-input"), "5");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("generate-quick-plan-button"));
    });

    await waitFor(() => expect(screen.getByTestId("quick-plan-error")).toBeTruthy());
    expect(mockCreateQuickPlan).not.toHaveBeenCalled();
  });

  it("saves the generated plan to a real collection", async () => {
    mockCreateQuickPlan.mockResolvedValue(makePlan());
    mockSaveQuickPlanToCollection.mockResolvedValue({
      collection_id: "col-1",
      collection_name: "Quick plan — 01 Jan 2026",
      item_count: 1,
    });

    await render(<QuickPlanScreen />);
    await act(async () => {
      fireEvent.press(screen.getByTestId("generate-quick-plan-button"));
    });
    await waitFor(() => expect(screen.getByTestId("save-quick-plan-button")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("save-quick-plan-button"));
    });

    await waitFor(() => expect(mockSaveQuickPlanToCollection).toHaveBeenCalledWith("plan-1"));
    expect(screen.getByText('Saved to "Quick plan — 01 Jan 2026"')).toBeTruthy();
  });
});
