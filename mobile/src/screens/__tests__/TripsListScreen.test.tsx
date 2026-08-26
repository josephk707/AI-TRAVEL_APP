import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { ApiError } from "../../api/client";
import { listTrips, Trip } from "../../api/trips";
import { TripsListScreen } from "../TripsListScreen";

const mockNavigate = jest.fn();
const mockAddListener = jest.fn((event: string, callback: () => void) => {
  if (event === "focus") callback();
  return () => {};
});
// A single stable object, not a new literal per call — matches the real
// @react-navigation/native useNavigation(), which returns a stable
// reference across renders. Recreating the object on every render would
// re-trigger any effect keyed on it, which is exactly what happened here
// (a real infinite-render loop, caught by actually running this test, not
// assumed away).
const mockNavigation = { navigate: mockNavigate, addListener: mockAddListener };
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => mockNavigation,
}));

jest.mock("../../api/trips", () => ({
  listTrips: jest.fn(),
}));

const mockListTrips = listTrips as jest.Mock;

function makeTrip(overrides: Partial<Trip> = {}): Trip {
  return {
    id: "trip-1",
    owner_id: "owner-1",
    title: "Agra Weekend",
    destination: "Agra, India",
    destination_lat: null,
    destination_lng: null,
    start_date: "2026-10-10",
    end_date: "2026-10-11",
    status: "draft",
    trip_type: "solo",
    budget_planned: 15000,
    budget_currency: "INR",
    generation_status: "none",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("TripsListScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("shows an empty state when there are no trips", async () => {
    mockListTrips.mockResolvedValue([]);

    await render(<TripsListScreen />);

    await waitFor(() => expect(screen.getByTestId("trips-empty")).toBeTruthy());
  });

  it("renders real trips returned by the backend", async () => {
    mockListTrips.mockResolvedValue([makeTrip()]);

    await render(<TripsListScreen />);

    await waitFor(() => expect(screen.getByTestId("trip-card-trip-1")).toBeTruthy());
    expect(screen.getByText("Agra Weekend")).toBeTruthy();
  });

  it("shows a typed error state with retry on failure", async () => {
    mockListTrips.mockRejectedValue(new ApiError(500, "Server exploded"));

    await render(<TripsListScreen />);

    await waitFor(() => expect(screen.getByTestId("trips-error")).toBeTruthy());
    expect(screen.getByText("Server exploded")).toBeTruthy();
  });

  it("navigates to TripCreation when '+ New trip' is pressed", async () => {
    mockListTrips.mockResolvedValue([]);

    await render(<TripsListScreen />);
    await waitFor(() => expect(screen.getByTestId("trips-empty")).toBeTruthy());

    fireEvent.press(screen.getByTestId("new-trip-button"));

    expect(mockNavigate).toHaveBeenCalledWith("TripCreation");
  });

  it("navigates to Chat for a trip with no itinerary yet", async () => {
    mockListTrips.mockResolvedValue([makeTrip({ generation_status: "none" })]);

    await render(<TripsListScreen />);
    await waitFor(() => expect(screen.getByTestId("trip-card-trip-1")).toBeTruthy());

    fireEvent.press(screen.getByTestId("trip-card-trip-1"));

    expect(mockNavigate).toHaveBeenCalledWith("Chat", { tripId: "trip-1" });
  });

  it("navigates to ItineraryView for a trip that already has a plan", async () => {
    mockListTrips.mockResolvedValue([makeTrip({ generation_status: "succeeded" })]);

    await render(<TripsListScreen />);
    await waitFor(() => expect(screen.getByTestId("trip-card-trip-1")).toBeTruthy());

    fireEvent.press(screen.getByTestId("trip-card-trip-1"));

    expect(mockNavigate).toHaveBeenCalledWith("ItineraryView", { tripId: "trip-1" });
  });
});
