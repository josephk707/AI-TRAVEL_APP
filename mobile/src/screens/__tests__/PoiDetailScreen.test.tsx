import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { ApiError } from "../../api/client";
import { fetchPoi } from "../../api/pois";
import { PoiDetailScreen } from "../PoiDetailScreen";

jest.mock("../../api/pois", () => ({
  fetchPoi: jest.fn(),
}));

const mockFetchPoi = fetchPoi as jest.Mock;

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => ({ navigate: mockNavigate }),
  useRoute: () => ({ params: { poiId: "11111111-1111-4111-8111-111111111111" } }),
}));

const TAJ_MAHAL = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Taj Mahal",
  category: "heritage",
  location: { lat: 27.1751, lng: 78.0421 },
  address: "Dharmapuri, Agra",
  city: "Agra",
  region: "Uttar Pradesh",
  country: "India",
  opening_hours: { monday: "06:00-19:00", tuesday: "closed" },
  avg_cost: 1100,
  source: "curated",
  is_heritage_flagship: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("PoiDetailScreen", () => {
  afterEach(() => jest.clearAllMocks());

  it("shows the loaded place's details", async () => {
    mockFetchPoi.mockResolvedValue(TAJ_MAHAL);

    await render(<PoiDetailScreen />);

    await waitFor(() => expect(screen.getByTestId("poi-detail-content")).toBeTruthy());
    expect(screen.getByText("Taj Mahal")).toBeTruthy();
    expect(screen.getByText("Dharmapuri, Agra")).toBeTruthy();
    expect(screen.getByText("₹1100")).toBeTruthy();
    expect(mockFetchPoi).toHaveBeenCalledWith("11111111-1111-4111-8111-111111111111");
  });

  it("shows 'verify on arrival' when opening hours are unknown", async () => {
    mockFetchPoi.mockResolvedValue({ ...TAJ_MAHAL, opening_hours: null });

    await render(<PoiDetailScreen />);

    await waitFor(() => expect(screen.getByTestId("poi-detail-content")).toBeTruthy());
    expect(screen.getByText("Not confirmed — verify on arrival")).toBeTruthy();
  });

  it("shows a typed error state when loading fails", async () => {
    mockFetchPoi.mockRejectedValue(new ApiError(404, "This place could not be found."));

    await render(<PoiDetailScreen />);

    await waitFor(() => expect(screen.getByTestId("poi-detail-error")).toBeTruthy());
    expect(screen.getByText("This place could not be found.")).toBeTruthy();
  });

  it("retries loading when the retry button is pressed", async () => {
    mockFetchPoi
      .mockRejectedValueOnce(new ApiError(503, "Backend unavailable"))
      .mockResolvedValueOnce(TAJ_MAHAL);

    await render(<PoiDetailScreen />);
    await waitFor(() => expect(screen.getByTestId("poi-detail-error")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("poi-detail-retry-button"));
    });

    await waitFor(() => expect(screen.getByTestId("poi-detail-content")).toBeTruthy());
    expect(screen.getByText("Taj Mahal")).toBeTruthy();
  });

  it("shows the heritage-story entry for a heritage-category place and navigates on press", async () => {
    mockFetchPoi.mockResolvedValue(TAJ_MAHAL);

    await render(<PoiDetailScreen />);
    await waitFor(() => expect(screen.getByTestId("heritage-story-button")).toBeTruthy());

    fireEvent.press(screen.getByTestId("heritage-story-button"));

    expect(mockNavigate).toHaveBeenCalledWith("HeritageNarration", {
      poiId: "11111111-1111-4111-8111-111111111111",
      poiName: "Taj Mahal",
    });
  });

  it("does not show the heritage-story entry for a non-heritage place", async () => {
    mockFetchPoi.mockResolvedValue({ ...TAJ_MAHAL, category: "restaurant" });

    await render(<PoiDetailScreen />);

    await waitFor(() => expect(screen.getByTestId("poi-detail-content")).toBeTruthy());
    expect(screen.queryByTestId("heritage-story-button")).toBeNull();
  });
});
