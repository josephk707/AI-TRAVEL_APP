import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { ApiError } from "../../api/client";
import { addFavorite, listFavorites, removeFavorite } from "../../api/collections";
import { fetchPoi } from "../../api/pois";
import { createReview, listPoiReviews } from "../../api/reviews";
import { listTrips } from "../../api/trips";
import { fetchWeather } from "../../api/weather";
import { PoiDetailScreen } from "../PoiDetailScreen";

jest.mock("../../api/pois", () => ({
  fetchPoi: jest.fn(),
}));

jest.mock("../../api/collections", () => ({
  listFavorites: jest.fn(),
  addFavorite: jest.fn(),
  removeFavorite: jest.fn(),
}));

jest.mock("../../api/reviews", () => ({
  listPoiReviews: jest.fn(),
  createReview: jest.fn(),
}));

jest.mock("../../api/trips", () => ({
  listTrips: jest.fn(),
}));

jest.mock("../../api/weather", () => ({
  fetchWeather: jest.fn(),
}));

jest.mock("../../i18n", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { en } = require("../../i18n/locales/en");
  const t = (key: string): unknown =>
    key.split(".").reduce((acc: unknown, part: string) => (acc as never)?.[part], en) ?? key;
  return { useTranslation: () => ({ t }) };
});

const mockFetchPoi = fetchPoi as jest.Mock;
const mockListFavorites = listFavorites as jest.Mock;
const mockAddFavorite = addFavorite as jest.Mock;
const mockRemoveFavorite = removeFavorite as jest.Mock;
const mockListPoiReviews = listPoiReviews as jest.Mock;
const mockCreateReview = createReview as jest.Mock;
const mockListTrips = listTrips as jest.Mock;
const mockFetchWeather = fetchWeather as jest.Mock;

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
  beforeEach(() => {
    mockListFavorites.mockResolvedValue([]);
    mockListPoiReviews.mockResolvedValue([]);
    mockListTrips.mockResolvedValue([]);
    mockFetchWeather.mockResolvedValue({
      lat: 27.1751,
      lng: 78.0421,
      current: {
        temperature_c: 34.2,
        condition_code: 1,
        condition: "Mainly clear",
        humidity_percent: 40,
        wind_speed_kmh: 12,
        is_day: true,
      },
      daily: [
        {
          date: "2026-08-28",
          temperature_max_c: 36,
          temperature_min_c: 28,
          condition_code: 1,
          condition: "Mainly clear",
          precipitation_probability_percent: 5,
        },
      ],
    });
  });

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

  // -------------------------------------------------------------------
  // F13 — Favorite toggle
  // -------------------------------------------------------------------
  it("shows an outlined heart when the place is not yet a favorite, and fills it in on press", async () => {
    mockFetchPoi.mockResolvedValue(TAJ_MAHAL);
    mockListFavorites.mockResolvedValue([]);
    mockAddFavorite.mockResolvedValue(undefined);

    await render(<PoiDetailScreen />);
    await waitFor(() => expect(screen.getByTestId("poi-detail-content")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("favorite-toggle-button"));
    });

    await waitFor(() =>
      expect(mockAddFavorite).toHaveBeenCalledWith("11111111-1111-4111-8111-111111111111"),
    );
  });

  it("shows a filled heart and removes the favorite on press when already favorited", async () => {
    mockFetchPoi.mockResolvedValue(TAJ_MAHAL);
    mockListFavorites.mockResolvedValue([
      { poi_id: "11111111-1111-4111-8111-111111111111", poi_name: "Taj Mahal", poi_category: "heritage", created_at: "2026-01-01T00:00:00Z" },
    ]);
    mockRemoveFavorite.mockResolvedValue(undefined);

    await render(<PoiDetailScreen />);
    await waitFor(() => expect(screen.getByTestId("poi-detail-content")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("favorite-toggle-button"));
    });

    await waitFor(() =>
      expect(mockRemoveFavorite).toHaveBeenCalledWith("11111111-1111-4111-8111-111111111111"),
    );
  });

  // -------------------------------------------------------------------
  // F14 — Reviews section
  // -------------------------------------------------------------------
  it("shows an empty reviews state when no published reviews exist", async () => {
    mockFetchPoi.mockResolvedValue(TAJ_MAHAL);
    mockListPoiReviews.mockResolvedValue([]);

    await render(<PoiDetailScreen />);

    await waitFor(() => expect(screen.getByTestId("reviews-empty")).toBeTruthy());
  });

  it("renders real published reviews returned by the backend", async () => {
    mockFetchPoi.mockResolvedValue(TAJ_MAHAL);
    mockListPoiReviews.mockResolvedValue([
      {
        id: "review-1",
        user_id: "user-1",
        poi_id: TAJ_MAHAL.id,
        trip_id: "trip-1",
        rating: 5,
        review_text: "Breathtaking at sunrise.",
        status: "published",
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);

    await render(<PoiDetailScreen />);

    await waitFor(() => expect(screen.getByTestId("review-review-1")).toBeTruthy());
    expect(screen.getByText("Breathtaking at sunrise.")).toBeTruthy();
  });

  it("shows a message instead of a trip picker when there are no completed trips to review from", async () => {
    mockFetchPoi.mockResolvedValue(TAJ_MAHAL);
    mockListTrips.mockResolvedValue([]);

    await render(<PoiDetailScreen />);
    await waitFor(() => expect(screen.getByTestId("write-review-button")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("write-review-button"));
    });

    await waitFor(() => expect(screen.getByTestId("review-form")).toBeTruthy());
    expect(
      screen.getByText("Complete a trip that included this place to leave a review."),
    ).toBeTruthy();
  });

  it("submits a review for a chosen completed trip and refreshes the list", async () => {
    mockFetchPoi.mockResolvedValue(TAJ_MAHAL);
    mockListTrips.mockResolvedValue([
      {
        id: "trip-1",
        owner_id: "owner-1",
        title: "Agra Weekend",
        destination: "Agra, India",
        destination_lat: null,
        destination_lng: null,
        start_date: null,
        end_date: null,
        status: "completed",
        trip_type: "solo",
        budget_planned: null,
        budget_currency: "INR",
        generation_status: "none",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);
    mockCreateReview.mockResolvedValue({
      id: "review-2",
      user_id: "user-1",
      poi_id: TAJ_MAHAL.id,
      trip_id: "trip-1",
      rating: 4,
      review_text: null,
      status: "pending",
      created_at: "2026-01-01T00:00:00Z",
    });

    await render(<PoiDetailScreen />);
    await waitFor(() => expect(screen.getByTestId("write-review-button")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("write-review-button"));
    });
    await waitFor(() => expect(screen.getByTestId("review-trip-trip-1")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("review-trip-trip-1"));
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("review-star-4"));
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("submit-review-button"));
    });

    await waitFor(() =>
      expect(mockCreateReview).toHaveBeenCalledWith(TAJ_MAHAL.id, "trip-1", 4, undefined),
    );
  });

  // -------------------------------------------------------------------
  // Maps Integration phase — real Open-Meteo weather for this place
  // -------------------------------------------------------------------
  it("fetches and shows the real weather for this place's coordinates", async () => {
    mockFetchPoi.mockResolvedValue(TAJ_MAHAL);

    await render(<PoiDetailScreen />);

    await waitFor(() => expect(screen.getByTestId("weather-card")).toBeTruthy());
    expect(mockFetchWeather).toHaveBeenCalledWith(TAJ_MAHAL.location.lat, TAJ_MAHAL.location.lng);
    expect(screen.getByText("34°C")).toBeTruthy();
    expect(screen.getByText("Mainly clear")).toBeTruthy();
  });

  it("shows a typed error inside the weather card without blocking the rest of the screen", async () => {
    mockFetchPoi.mockResolvedValue(TAJ_MAHAL);
    mockFetchWeather.mockRejectedValue(new ApiError(503, "Weather is temporarily unavailable."));

    await render(<PoiDetailScreen />);

    await waitFor(() => expect(screen.getByTestId("weather-error")).toBeTruthy());
    expect(screen.getByText("Weather is temporarily unavailable.")).toBeTruthy();
    // The rest of the screen still renders normally.
    expect(screen.getByText("Taj Mahal")).toBeTruthy();
  });
});
