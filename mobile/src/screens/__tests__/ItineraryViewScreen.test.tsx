import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { ApiError } from "../../api/client";
import { fetchOfflinePackage } from "../../api/offline";
import { fetchItinerary, fetchTrip, ItineraryDay, Trip } from "../../api/trips";
import { ItineraryViewScreen } from "../ItineraryViewScreen";

const mockNavigate = jest.fn();
const mockNavigation = { navigate: mockNavigate, goBack: jest.fn() };
const mockRoute = { params: { tripId: "trip-1" } };
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => mockNavigation,
  useRoute: () => mockRoute,
}));

jest.mock("../../i18n", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { en } = require("../../i18n/locales/en");
  const t = (key: string): unknown =>
    key.split(".").reduce((acc: unknown, part: string) => (acc as never)?.[part], en) ?? key;
  return { useTranslation: () => ({ t }) };
});

jest.mock("../../api/trips", () => ({
  fetchTrip: jest.fn(),
  fetchItinerary: jest.fn(),
}));

jest.mock("../../api/offline", () => ({
  fetchOfflinePackage: jest.fn(),
}));

const mockFileWrite = jest.fn();
const mockFileCreate = jest.fn();
const mockDirectoryCreate = jest.fn();
jest.mock("expo-file-system", () => ({
  Directory: jest.fn().mockImplementation(() => ({
    exists: false,
    create: mockDirectoryCreate,
  })),
  File: jest.fn().mockImplementation(() => ({
    exists: false,
    create: mockFileCreate,
    write: mockFileWrite,
  })),
  Paths: { document: "file:///document/" },
}));

const mockFetchTrip = fetchTrip as jest.Mock;
const mockFetchItinerary = fetchItinerary as jest.Mock;
const mockFetchOfflinePackage = fetchOfflinePackage as jest.Mock;

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

  // -------------------------------------------------------------------
  // F26 — Offline Heritage Access ("Download for offline")
  // -------------------------------------------------------------------
  it("downloads the real offline package and persists it locally", async () => {
    mockFetchTrip.mockResolvedValue(makeTrip());
    mockFetchItinerary.mockResolvedValue([makeDay()]);
    mockFetchOfflinePackage.mockResolvedValue({
      trip_id: "trip-1",
      packaged_at: "2026-01-01T00:00:00Z",
      pois: [{ poi_id: "poi-1", name: "Taj Mahal", category: "heritage", lat: 27.17, lng: 78.04 }],
      heritage_content: [
        { poi_id: "poi-1", section_title: "Overview", body_text: "...", source_citation: "ASI" },
      ],
      phrasebook_entries: [],
    });

    await render(<ItineraryViewScreen />);
    await waitFor(() => expect(screen.getByTestId("download-offline-button")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("download-offline-button"));
    });

    await waitFor(() => expect(mockFetchOfflinePackage).toHaveBeenCalledWith("trip-1"));
    await waitFor(() => expect(mockFileWrite).toHaveBeenCalled());
    expect(screen.getByTestId("download-message")).toBeTruthy();
  });

  it("shows a typed error message when the offline download fails", async () => {
    mockFetchTrip.mockResolvedValue(makeTrip());
    mockFetchItinerary.mockResolvedValue([makeDay()]);
    mockFetchOfflinePackage.mockRejectedValue(new ApiError(500, "Server exploded"));

    await render(<ItineraryViewScreen />);
    await waitFor(() => expect(screen.getByTestId("download-offline-button")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("download-offline-button"));
    });

    await waitFor(() => expect(screen.getByText("Server exploded")).toBeTruthy());
  });
});
