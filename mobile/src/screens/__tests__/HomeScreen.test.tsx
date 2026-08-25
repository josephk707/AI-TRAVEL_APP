import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { bootstrapSession, fetchMyProfile, ProfileData } from "../../api/auth";
import { ApiError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { HomeScreen } from "../HomeScreen";

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => ({ navigate: mockNavigate }),
}));

jest.mock("../../auth/AuthContext", () => ({
  useAuth: jest.fn(),
}));

jest.mock("../../api/auth", () => ({
  bootstrapSession: jest.fn(),
  fetchMyProfile: jest.fn(),
}));

const mockUseAuth = useAuth as jest.Mock;
const mockBootstrapSession = bootstrapSession as jest.Mock;
const mockFetchMyProfile = fetchMyProfile as jest.Mock;

const PROFILE: ProfileData = {
  id: "11111111-1111-4111-8111-111111111111",
  display_name: null,
  avatar_url: null,
  home_region: null,
  travel_style: null,
  pace: null,
  budget_bracket: null,
  role: "traveller",
  onboarding_completed_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("HomeScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuth.mockReturnValue({
      state: "AUTHENTICATED",
      session: null,
      user: { id: PROFILE.id, email: "traveller@example.com" },
      errorMessage: null,
      signInWithGoogle: jest.fn(),
      signOut: jest.fn(),
      clearError: jest.fn(),
    });
  });

  it("bootstraps the session and renders the real profile fetched from the backend", async () => {
    mockBootstrapSession.mockResolvedValue({ profile: PROFILE, created: false });
    mockFetchMyProfile.mockResolvedValue(PROFILE);

    await render(<HomeScreen />);

    await waitFor(() => expect(screen.getByTestId("profile-success")).toBeTruthy());
    expect(mockBootstrapSession).toHaveBeenCalled();
    expect(mockFetchMyProfile).toHaveBeenCalled();
    expect(screen.getByText(`User ID: ${PROFILE.id}`)).toBeTruthy();
    expect(screen.getByText("Role: traveller")).toBeTruthy();
  });

  it("shows a typed error state with retry when loading the profile fails", async () => {
    mockBootstrapSession.mockRejectedValue(new ApiError(503, "Backend unavailable"));

    await render(<HomeScreen />);

    await waitFor(() => expect(screen.getByTestId("profile-error")).toBeTruthy());
    expect(screen.getByText("Backend unavailable")).toBeTruthy();
    expect(screen.getByTestId("profile-retry-button")).toBeTruthy();
  });

  it("retries loading the profile when the retry button is pressed", async () => {
    mockBootstrapSession
      .mockRejectedValueOnce(new ApiError(503, "Backend unavailable"))
      .mockResolvedValueOnce({ profile: PROFILE, created: false });
    mockFetchMyProfile.mockResolvedValue(PROFILE);

    await render(<HomeScreen />);
    await waitFor(() => expect(screen.getByTestId("profile-error")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("profile-retry-button"));
    });

    await waitFor(() => expect(screen.getByTestId("profile-success")).toBeTruthy());
  });

  it("calls signOut() when the sign-out button is pressed", async () => {
    mockBootstrapSession.mockResolvedValue({ profile: PROFILE, created: false });
    mockFetchMyProfile.mockResolvedValue(PROFILE);
    const signOut = jest.fn();
    mockUseAuth.mockReturnValue({
      state: "AUTHENTICATED",
      session: null,
      user: { id: PROFILE.id, email: "traveller@example.com" },
      errorMessage: null,
      signInWithGoogle: jest.fn(),
      signOut,
      clearError: jest.fn(),
    });

    await render(<HomeScreen />);
    await waitFor(() => expect(screen.getByTestId("profile-success")).toBeTruthy());

    fireEvent.press(screen.getByTestId("sign-out-button"));

    expect(signOut).toHaveBeenCalled();
  });

  it("navigates to Explore when the explore-places card is pressed", async () => {
    mockBootstrapSession.mockResolvedValue({ profile: PROFILE, created: false });
    mockFetchMyProfile.mockResolvedValue(PROFILE);

    await render(<HomeScreen />);
    await waitFor(() => expect(screen.getByTestId("profile-success")).toBeTruthy());

    fireEvent.press(screen.getByTestId("explore-places-button"));

    expect(mockNavigate).toHaveBeenCalledWith("Explore");
  });
});
