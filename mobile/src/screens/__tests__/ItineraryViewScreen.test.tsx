import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { ApiError } from "../../api/client";
import { fetchItinerary, fetchTrip, ItineraryDay, Trip } from "../../api/trips";
import { ItineraryViewScreen } from "../ItineraryViewScreen";

const mockNavigate = jest.fn();
const mockNavigation = { navigate: mockNavigate };
const mockRoute = { params: { tripId: "trip-1" } };
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => mockNavigation,
  useRoute: () => mockRoute,
}));

jest.mock("../../api/trips", () => ({
  fetchTrip: jest.fn(),
  fetchItinerary: jest.fn(),
}));

const mockFetchTrip = fetchTrip as jest.Mock;
const mockFetchItinerary = fetchItinerary as jest.Mock;

function makeTrip(overrides: Partial<Trip> = {}): Trip {
  return {
    id: "trip-1",
    owner_id: "owner-1",
    title: "Agra Weekend",
    destination: "Agra, India",
    destination_lat: null,
    destination_lng: null,
    start_date: "2026-10-10",
    end_date: "2026-10-10",
    status: "draft",
    trip_type: "solo",
    budget_planned: 15000,
    budget_currency: "INR",
    generation_status: "succeeded",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeDay(overrides: Partial<ItineraryDay> = {}): ItineraryDay {
  return {
    day_number: 1,
    date: "2026-10-10",
    items: [
      {
        id: "item-1",
        poi_id: "poi-1",
        poi_name: "Taj Mahal",
        sequence_order: 0,
        planned_start: "06:00",
        planned_end: "08:30",
        estimated_duration_min: 150,
        estimated_cost: 1100,
        status: "planned",
        source: "ai",
        verify_on_arrival: true,
        weather_flag: false,
        weather_alternative_suggestion: null,
        notes: null,
      },
    ],
    ...overrides,
  };
}

describe("ItineraryViewScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders the real itinerary with day headings and item detail", async () => {
    mockFetchTrip.mockResolvedValue(makeTrip());
    mockFetchItinerary.mockResolvedValue([makeDay()]);

    await render(<ItineraryViewScreen />);

    await waitFor(() => expect(screen.getByTestId("item-item-1")).toBeTruthy());
    expect(screen.getByText("Day 1 · 2026-10-10")).toBeTruthy();
    expect(screen.getByText("Taj Mahal")).toBeTruthy();
    expect(screen.getByText("Verify hours on arrival")).toBeTruthy();
  });

  it("shows an empty state when there are no itinerary items yet", async () => {
    mockFetchTrip.mockResolvedValue(makeTrip());
    mockFetchItinerary.mockResolvedValue([]);

    await render(<ItineraryViewScreen />);

    await waitFor(() => expect(screen.getByTestId("itinerary-empty")).toBeTruthy());
  });

  it("shows a typed error state with retry on failure", async () => {
    mockFetchTrip.mockRejectedValue(new ApiError(500, "Server exploded"));
    mockFetchItinerary.mockResolvedValue([]);

    await render(<ItineraryViewScreen />);

    await waitFor(() => expect(screen.getByTestId("itinerary-error")).toBeTruthy());
    expect(screen.getByText("Server exploded")).toBeTruthy();
  });

  it("navigates to Chat when the adjust-plan FAB is pressed", async () => {
    mockFetchTrip.mockResolvedValue(makeTrip());
    mockFetchItinerary.mockResolvedValue([makeDay()]);

    await render(<ItineraryViewScreen />);
    await waitFor(() => expect(screen.getByTestId("open-chat-fab")).toBeTruthy());

    fireEvent.press(screen.getByTestId("open-chat-fab"));

    expect(mockNavigate).toHaveBeenCalledWith("Chat", { tripId: "trip-1" });
  });
});
