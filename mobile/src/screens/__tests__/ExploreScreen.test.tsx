import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import * as Location from "expo-location";
import React from "react";

import { ApiError } from "../../api/client";
import { fetchNearbyPois, searchPois } from "../../api/pois";
import { ExploreScreen } from "../ExploreScreen";

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => ({ navigate: mockNavigate }),
}));

jest.mock("../../api/pois", () => ({
  searchPois: jest.fn(),
  fetchNearbyPois: jest.fn(),
}));

jest.mock("expo-location", () => ({
  requestForegroundPermissionsAsync: jest.fn(),
  getCurrentPositionAsync: jest.fn(),
}));

jest.mock("../../i18n", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { en } = require("../../i18n/locales/en");
  const t = (key: string): unknown =>
    key.split(".").reduce((acc: unknown, part: string) => (acc as never)?.[part], en) ?? key;
  return { useTranslation: () => ({ t }) };
});

const mockSearchPois = searchPois as jest.Mock;
const mockFetchNearbyPois = fetchNearbyPois as jest.Mock;
const mockRequestPermission = Location.requestForegroundPermissionsAsync as jest.Mock;
const mockGetCurrentPosition = Location.getCurrentPositionAsync as jest.Mock;

const HERITAGE_POI = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Taj Mahal",
  category: "heritage",
  location: { lat: 27.1751, lng: 78.0421 },
  address: "Agra",
  city: "Agra",
  region: "Uttar Pradesh",
  country: "India",
  opening_hours: null,
  avg_cost: null,
  source: "curated",
  is_heritage_flagship: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

async function submitSearch(text: string): Promise<void> {
  // Two SEPARATE act() cycles, not one: within a single cycle React
  // batches both fireEvent calls before re-rendering, so the
  // onSubmitEditing handler (recreated via useCallback on every render)
  // would still close over the PRE-change `queryText` (empty string) and
  // hit the "nothing to search" early-return guard — a real bug in this
  // helper that silently left every test stuck on the idle state, not an
  // app bug. Awaiting the change separately forces the re-render (and a
  // fresh handleSubmit closure) before submitEditing fires. The async
  // act() wrapping itself is still required too — the resulting search's
  // state updates happen outside any act() scope otherwise, corrupting
  // this environment's act-tracking for every later test in the file
  // (same root-cause class as onboardingStore.test.ts /
  // InterestSelectScreen.test.tsx).
  await act(async () => {
    fireEvent.changeText(screen.getByTestId("explore-search-input"), text);
  });
  await act(async () => {
    fireEvent(screen.getByTestId("explore-search-input"), "submitEditing");
  });
}

describe("ExploreScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("shows the idle prompt before any search is submitted", async () => {
    await render(<ExploreScreen />);

    expect(screen.getByTestId("explore-empty-prompt")).toBeTruthy();
    expect(mockSearchPois).not.toHaveBeenCalled();
  });

  it("shows results as PoiCards after a successful search", async () => {
    mockSearchPois.mockResolvedValue({ pois: [HERITAGE_POI], degraded: false, message: null });
    await render(<ExploreScreen />);

    await submitSearch("Taj Mahal");

    await waitFor(() => expect(screen.getByTestId("explore-results-list")).toBeTruthy());
    expect(screen.getByTestId(`poi-card-${HERITAGE_POI.id}`)).toBeTruthy();
    expect(mockSearchPois).toHaveBeenCalledWith(
      expect.objectContaining({ query: "Taj Mahal", category: undefined }),
    );
  });

  it("shows an empty state when the search succeeds with no results", async () => {
    mockSearchPois.mockResolvedValue({ pois: [], degraded: false, message: null });
    await render(<ExploreScreen />);

    await submitSearch("nonexistent place");

    await waitFor(() => expect(screen.getByTestId("explore-no-results")).toBeTruthy());
  });

  it("shows a typed error state with retry when the search fails", async () => {
    mockSearchPois.mockRejectedValue(new ApiError(503, "Backend unavailable"));
    await render(<ExploreScreen />);

    await submitSearch("Taj Mahal");

    await waitFor(() => expect(screen.getByTestId("explore-error")).toBeTruthy());
    expect(screen.getByText("Backend unavailable")).toBeTruthy();

    mockSearchPois.mockResolvedValue({ pois: [HERITAGE_POI], degraded: false, message: null });
    await act(async () => {
      fireEvent.press(screen.getByTestId("explore-retry-button"));
    });

    await waitFor(() => expect(screen.getByTestId("explore-results-list")).toBeTruthy());
  });

  it("shows the degraded-mode banner when the backend flags degraded results", async () => {
    mockSearchPois.mockResolvedValue({
      pois: [HERITAGE_POI],
      degraded: true,
      message: "Live search is temporarily unavailable — showing curated results only.",
    });
    await render(<ExploreScreen />);

    await submitSearch("Taj Mahal");

    await waitFor(() => expect(screen.getByTestId("explore-degraded-banner")).toBeTruthy());
    expect(
      screen.getByText("Live search is temporarily unavailable — showing curated results only."),
    ).toBeTruthy();
  });

  it("re-runs the search with the selected category when a filter chip is pressed", async () => {
    mockSearchPois.mockResolvedValue({ pois: [HERITAGE_POI], degraded: false, message: null });
    await render(<ExploreScreen />);

    await submitSearch("places");
    await waitFor(() => expect(screen.getByTestId("explore-results-list")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("explore-category-heritage"));
    });

    await waitFor(() =>
      expect(mockSearchPois).toHaveBeenLastCalledWith(
        expect.objectContaining({ query: "places", category: "heritage" }),
      ),
    );
  });

  it("navigates to PoiDetail with the pressed card's id", async () => {
    mockSearchPois.mockResolvedValue({ pois: [HERITAGE_POI], degraded: false, message: null });
    await render(<ExploreScreen />);

    await submitSearch("Taj Mahal");
    await waitFor(() => expect(screen.getByTestId("explore-results-list")).toBeTruthy());

    fireEvent.press(screen.getByTestId(`poi-card-${HERITAGE_POI.id}`));

    expect(mockNavigate).toHaveBeenCalledWith("PoiDetail", { poiId: HERITAGE_POI.id });
  });

  // -------------------------------------------------------------------
  // Maps Integration phase — "use my location" (real device location ->
  // GET /v1/pois/nearby, live-augmented via Geoapify on the backend)
  // -------------------------------------------------------------------
  it("requests location and shows real nearby places when granted", async () => {
    mockRequestPermission.mockResolvedValue({ granted: true });
    mockGetCurrentPosition.mockResolvedValue({
      coords: { latitude: 12.3052, longitude: 76.6552 },
    });
    mockFetchNearbyPois.mockResolvedValue({
      pois: [HERITAGE_POI],
      degraded: false,
      message: null,
    });

    await render(<ExploreScreen />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("explore-locate-button"));
    });

    await waitFor(() => expect(screen.getByTestId("explore-results-list")).toBeTruthy());
    expect(mockFetchNearbyPois).toHaveBeenCalledWith(
      expect.objectContaining({ lat: 12.3052, lng: 76.6552, radiusM: 5000 }),
    );
    expect(screen.getByTestId(`poi-card-${HERITAGE_POI.id}`)).toBeTruthy();
  });

  it("shows a typed error state when location permission is denied", async () => {
    mockRequestPermission.mockResolvedValue({ granted: false });

    await render(<ExploreScreen />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("explore-locate-button"));
    });

    await waitFor(() => expect(screen.getByTestId("explore-error")).toBeTruthy());
    expect(mockFetchNearbyPois).not.toHaveBeenCalled();
  });

  it("shows the degraded-mode banner when nearby live augmentation is unavailable", async () => {
    mockRequestPermission.mockResolvedValue({ granted: true });
    mockGetCurrentPosition.mockResolvedValue({
      coords: { latitude: 12.3052, longitude: 76.6552 },
    });
    mockFetchNearbyPois.mockResolvedValue({
      pois: [HERITAGE_POI],
      degraded: true,
      message: "Live nearby search is temporarily unavailable — showing curated results only.",
    });

    await render(<ExploreScreen />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("explore-locate-button"));
    });

    await waitFor(() => expect(screen.getByTestId("explore-degraded-banner")).toBeTruthy());
  });
});
