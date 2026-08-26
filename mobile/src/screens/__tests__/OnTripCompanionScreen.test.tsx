import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import * as Location from "expo-location";
import React from "react";

import { ApiError } from "../../api/client";
import {
  fetchNearby,
  setLocationConsent,
  submitLocationPing,
  submitManualLocation,
} from "../../api/location";
import { fetchItinerary } from "../../api/trips";
import { OnTripCompanionScreen } from "../OnTripCompanionScreen";

jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useRoute: () => ({ params: { tripId: "trip-1" } }),
}));

jest.mock("../../api/trips", () => ({
  fetchItinerary: jest.fn(),
}));

jest.mock("../../api/location", () => ({
  setLocationConsent: jest.fn(),
  submitLocationPing: jest.fn(),
  submitManualLocation: jest.fn(),
  fetchNearby: jest.fn(),
}));

jest.mock("expo-location", () => ({
  Accuracy: { Balanced: 3 },
  requestForegroundPermissionsAsync: jest.fn(),
  getCurrentPositionAsync: jest.fn(),
  watchPositionAsync: jest.fn().mockResolvedValue({ remove: jest.fn() }),
}));

const mockFetchItinerary = fetchItinerary as jest.Mock;
const mockSetLocationConsent = setLocationConsent as jest.Mock;
const mockSubmitLocationPing = submitLocationPing as jest.Mock;
const mockSubmitManualLocation = submitManualLocation as jest.Mock;
const mockFetchNearby = fetchNearby as jest.Mock;
const mockRequestForeground = Location.requestForegroundPermissionsAsync as jest.Mock;
const mockGetCurrentPosition = Location.getCurrentPositionAsync as jest.Mock;

function makeItem(overrides: Record<string, unknown> = {}) {
  return {
    id: "item-1",
    poi_id: "poi-1",
    poi_name: "Taj Mahal",
    sequence_order: 0,
    planned_start: "09:00",
    planned_end: "11:00",
    estimated_duration_min: 120,
    estimated_cost: null,
    status: "planned",
    source: "ai",
    verify_on_arrival: false,
    weather_flag: false,
    weather_alternative_suggestion: null,
    notes: null,
    ...overrides,
  };
}

describe("OnTripCompanionScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockRequestForeground.mockResolvedValue({ granted: true });
  });

  it("shows the consent switch off by default, gating the check-in button", async () => {
    mockFetchItinerary.mockResolvedValue([{ day_number: 1, date: null, items: [makeItem()] }]);

    await render(<OnTripCompanionScreen />);

    await waitFor(() => expect(screen.getByTestId("remaining-stops-list")).toBeTruthy());
    expect(screen.getByTestId("location-consent-switch").props.value).toBe(false);
    expect(screen.getByTestId("check-in-button").props.accessibilityState?.disabled).toBe(true);
  });

  it("shows remaining stops and lets the traveller confirm arrival manually", async () => {
    mockFetchItinerary.mockResolvedValue([{ day_number: 1, date: null, items: [makeItem()] }]);
    mockSubmitManualLocation.mockResolvedValue({
      arrival_event: { itinerary_item_id: "item-1", poi_name: "Taj Mahal" },
      nearby: [],
    });

    await render(<OnTripCompanionScreen />);
    await waitFor(() => expect(screen.getByTestId("manual-arrival-item-1")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("manual-arrival-item-1"));
    });

    await waitFor(() => expect(mockSubmitManualLocation).toHaveBeenCalledWith("trip-1", "poi-1"));
    await waitFor(() => expect(screen.getByTestId("arrival-banner")).toBeTruthy());
  });

  it("shows an empty state when every stop is already complete", async () => {
    mockFetchItinerary.mockResolvedValue([
      { day_number: 1, date: null, items: [makeItem({ status: "completed" })] },
    ]);

    await render(<OnTripCompanionScreen />);

    await waitFor(() => expect(screen.getByTestId("on-trip-empty")).toBeTruthy());
  });

  it("shows a typed error state with retry on failure", async () => {
    mockFetchItinerary.mockRejectedValue(new ApiError(500, "Server exploded"));

    await render(<OnTripCompanionScreen />);

    await waitFor(() => expect(screen.getByTestId("on-trip-error")).toBeTruthy());
    expect(screen.getByText("Server exploded")).toBeTruthy();
  });

  it("enables consent, then checks in and surfaces nearby recommendations", async () => {
    mockFetchItinerary.mockResolvedValue([{ day_number: 1, date: null, items: [makeItem()] }]);
    mockSetLocationConsent.mockResolvedValue(undefined);
    mockGetCurrentPosition.mockResolvedValue({ coords: { latitude: 27.17, longitude: 78.04 } });
    mockSubmitLocationPing.mockResolvedValue({ arrival_event: null, nearby: [] });
    mockFetchNearby.mockResolvedValue([{ poi_id: "poi-2", name: "Agra Fort", distance_m: 500 }]);

    await render(<OnTripCompanionScreen />);
    await waitFor(() => expect(screen.getByTestId("remaining-stops-list")).toBeTruthy());

    await act(async () => {
      fireEvent(screen.getByTestId("location-consent-switch"), "valueChange", true);
    });
    await waitFor(() => expect(mockSetLocationConsent).toHaveBeenCalledWith("trip-1", true));

    await act(async () => {
      fireEvent.press(screen.getByTestId("check-in-button"));
    });

    await waitFor(() => expect(mockSubmitLocationPing).toHaveBeenCalledWith("trip-1", 27.17, 78.04));
    await waitFor(() => expect(screen.getByTestId("nearby-section")).toBeTruthy());
    expect(screen.getByText("Agra Fort · 500m away")).toBeTruthy();
  });
});
