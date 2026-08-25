import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { fetchInterests, submitOnboardingResponses } from "../../../api/onboarding";
import { ApiError } from "../../../api/client";
import { useAuth } from "../../../auth/AuthContext";
import { useOnboardingStore } from "../../../onboarding/onboardingStore";
import { InterestSelectScreen } from "../InterestSelectScreen";

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => ({ navigate: mockNavigate }),
}));

jest.mock("../../../api/onboarding", () => ({
  fetchInterests: jest.fn(),
  submitOnboardingResponses: jest.fn(),
}));

jest.mock("../../../auth/AuthContext", () => ({
  useAuth: jest.fn(),
}));

const mockFetchInterests = fetchInterests as jest.Mock;
const mockSubmitOnboardingResponses = submitOnboardingResponses as jest.Mock;
const mockUseAuth = useAuth as jest.Mock;

const INTERESTS = [
  { id: 1, slug: "heritage", label: "Heritage & History" },
  { id: 2, slug: "food", label: "Food & Cuisine" },
];

describe("InterestSelectScreen", () => {
  const completeOnboardingLocally = jest.fn();

  beforeEach(async () => {
    jest.clearAllMocks();
    // Must be an awaited async act(): a synchronous act() here leaves this
    // React 19 + test-renderer environment's internal act-tracking in a bad
    // state (root-caused via the same class of bug documented in
    // onboardingStore.test.ts), which silently breaks the NEXT render()
    // call in this test file — the component mounts to an empty tree with
    // no hooks/effects ever firing, no error, no warning.
    await act(async () => {
      useOnboardingStore.getState().reset();
    });
    mockUseAuth.mockReturnValue({ completeOnboardingLocally });
  });

  it("shows a loading state, then renders the fetched interests as chips", async () => {
    mockFetchInterests.mockResolvedValue(INTERESTS);
    await render(<InterestSelectScreen />);

    await waitFor(() => expect(screen.getByTestId("interests-grid")).toBeTruthy());
    expect(screen.getByTestId("interest-chip-heritage")).toBeTruthy();
    expect(screen.getByTestId("interest-chip-food")).toBeTruthy();
  });

  it("shows a typed error state with retry when loading interests fails", async () => {
    mockFetchInterests.mockRejectedValue(new ApiError(503, "Backend unavailable"));
    await render(<InterestSelectScreen />);

    await waitFor(() => expect(screen.getByTestId("interests-error")).toBeTruthy());
    expect(screen.getByText("Backend unavailable")).toBeTruthy();
  });

  it("retries loading interests when the retry button is pressed", async () => {
    mockFetchInterests
      .mockRejectedValueOnce(new ApiError(503, "Backend unavailable"))
      .mockResolvedValueOnce(INTERESTS);
    await render(<InterestSelectScreen />);
    await waitFor(() => expect(screen.getByTestId("interests-error")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("interests-retry-button"));
    });

    await waitFor(() => expect(screen.getByTestId("interests-grid")).toBeTruthy());
  });

  it("toggles an interest's selected state when its chip is pressed", async () => {
    mockFetchInterests.mockResolvedValue(INTERESTS);
    await render(<InterestSelectScreen />);
    await waitFor(() => expect(screen.getByTestId("interests-grid")).toBeTruthy());

    fireEvent.press(screen.getByTestId("interest-chip-heritage"));

    expect(useOnboardingStore.getState().interestIds).toEqual([1]);
  });

  it("Continue navigates to TravelStyle without submitting anything", async () => {
    mockFetchInterests.mockResolvedValue(INTERESTS);
    await render(<InterestSelectScreen />);
    await waitFor(() => expect(screen.getByTestId("interests-grid")).toBeTruthy());

    fireEvent.press(screen.getByTestId("interest-continue-button"));

    expect(mockNavigate).toHaveBeenCalledWith("TravelStyle");
    expect(mockSubmitOnboardingResponses).not.toHaveBeenCalled();
  });

  it("Skip submits the current (possibly empty) selection and marks onboarding complete locally", async () => {
    mockFetchInterests.mockResolvedValue(INTERESTS);
    mockSubmitOnboardingResponses.mockResolvedValue({
      data: {
        onboarding_completed: true,
        onboarding_completed_at: "2026-01-01T00:00:00Z",
        interest_ids: [],
        travel_style: null,
        pace: null,
        budget_bracket: null,
      },
      saved: true,
    });
    await render(<InterestSelectScreen />);
    await waitFor(() => expect(screen.getByTestId("interests-grid")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("onboarding-skip-link"));
    });

    expect(mockSubmitOnboardingResponses).toHaveBeenCalledWith(
      expect.objectContaining({ interest_ids: [] }),
    );
    await waitFor(() => expect(completeOnboardingLocally).toHaveBeenCalled());
  });
});
