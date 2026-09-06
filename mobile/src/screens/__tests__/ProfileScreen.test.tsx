import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { fetchMyProfile, ProfileData } from "../../api/auth";
import { ApiError } from "../../api/client";
import { fetchTravelDna, TravelDna } from "../../api/personalization";
import { useAuth } from "../../auth/AuthContext";
import { ProfileScreen } from "../ProfileScreen";

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => ({ navigate: mockNavigate }),
}));

jest.mock("../../auth/AuthContext", () => ({
  useAuth: jest.fn(),
}));

jest.mock("../../api/auth", () => ({
  fetchMyProfile: jest.fn(),
}));

jest.mock("../../api/personalization", () => ({
  fetchTravelDna: jest.fn(),
}));

jest.mock("../../i18n", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { en } = require("../../i18n/locales/en");
  const t = (key: string): unknown =>
    key.split(".").reduce((acc: unknown, part: string) => (acc as never)?.[part], en) ?? key;
  return { useTranslation: () => ({ t }) };
});

const mockUseAuth = useAuth as jest.Mock;
const mockFetchMyProfile = fetchMyProfile as jest.Mock;
const mockFetchTravelDna = fetchTravelDna as jest.Mock;

const TRAVEL_DNA: TravelDna = {
  travel_style: "planned",
  pace: "balanced",
  budget_bracket: "mid",
  travel_companion: "solo",
  trip_motivation: null,
  interests: ["Heritage", "Food"],
  favorite_categories: {},
  trips_planned: 2,
  places_saved: 3,
  travel_personality: "Cultural Explorer",
  summary: "You enjoy heritage sites and local food.",
  generated_by: "template",
  updated_at: "2026-01-01T00:00:00Z",
};

const PROFILE: ProfileData = {
  id: "11111111-1111-4111-8111-111111111111",
  display_name: "Meera",
  avatar_url: null,
  home_region: null,
  travel_style: null,
  pace: null,
  budget_bracket: null,
  travel_companion: null,
  trip_motivation: null,
  role: "traveller",
  preferred_language: "en",
  onboarding_completed_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("ProfileScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: { id: PROFILE.id, email: "meera@example.com" } });
    mockFetchTravelDna.mockResolvedValue(TRAVEL_DNA);
  });

  it("renders the real profile fetched from the backend", async () => {
    mockFetchMyProfile.mockResolvedValue(PROFILE);

    await render(<ProfileScreen />);

    await waitFor(() => expect(screen.getByTestId("profile-success")).toBeTruthy());
    expect(screen.getByText("Meera")).toBeTruthy();
    expect(screen.getByText("meera@example.com")).toBeTruthy();
  });

  it("renders the real Travel DNA fetched from the backend", async () => {
    mockFetchMyProfile.mockResolvedValue(PROFILE);

    await render(<ProfileScreen />);

    await waitFor(() => expect(screen.getByTestId("travel-dna-success")).toBeTruthy());
    expect(screen.getByText("Cultural Explorer")).toBeTruthy();
    expect(screen.getByText("You enjoy heritage sites and local food.")).toBeTruthy();
  });

  it("shows a typed error state with retry when Travel DNA loading fails", async () => {
    mockFetchMyProfile.mockResolvedValue(PROFILE);
    mockFetchTravelDna.mockRejectedValue(new ApiError(503, "DNA unavailable"));

    await render(<ProfileScreen />);

    await waitFor(() => expect(screen.getByText("DNA unavailable")).toBeTruthy());

    mockFetchTravelDna.mockResolvedValue(TRAVEL_DNA);
    await act(async () => {
      fireEvent.press(screen.getAllByText("Retry")[0]);
    });

    await waitFor(() => expect(screen.getByTestId("travel-dna-success")).toBeTruthy());
  });

  it("shows a typed error state with retry when loading fails", async () => {
    mockFetchMyProfile.mockRejectedValue(new ApiError(503, "Backend unavailable"));

    await render(<ProfileScreen />);

    await waitFor(() => expect(screen.getByText("Backend unavailable")).toBeTruthy());

    mockFetchMyProfile.mockResolvedValue(PROFILE);
    await act(async () => {
      fireEvent.press(screen.getByText("Retry"));
    });

    await waitFor(() => expect(screen.getByTestId("profile-success")).toBeTruthy());
  });

  it("navigates to Settings when the settings link is pressed", async () => {
    mockFetchMyProfile.mockResolvedValue(PROFILE);
    await render(<ProfileScreen />);
    await waitFor(() => expect(screen.getByTestId("profile-success")).toBeTruthy());

    fireEvent.press(screen.getByText("Settings"));

    expect(mockNavigate).toHaveBeenCalledWith("Settings");
  });

  it("navigates to TripsList when the my-trips link is pressed", async () => {
    mockFetchMyProfile.mockResolvedValue(PROFILE);
    await render(<ProfileScreen />);
    await waitFor(() => expect(screen.getByTestId("profile-success")).toBeTruthy());

    fireEvent.press(screen.getByText("My trips"));

    expect(mockNavigate).toHaveBeenCalledWith("TripsList");
  });
});
