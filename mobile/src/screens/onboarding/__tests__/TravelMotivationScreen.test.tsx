import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { submitOnboardingResponses } from "../../../api/onboarding";
import { useAuth } from "../../../auth/AuthContext";
import { useOnboardingStore } from "../../../onboarding/onboardingStore";
import { TravelMotivationScreen } from "../TravelMotivationScreen";

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => ({ navigate: mockNavigate }),
}));

jest.mock("../../../api/onboarding", () => ({
  submitOnboardingResponses: jest.fn(),
}));

jest.mock("../../../auth/AuthContext", () => ({
  useAuth: jest.fn(),
}));

const mockSubmitOnboardingResponses = submitOnboardingResponses as jest.Mock;
const mockUseAuth = useAuth as jest.Mock;

describe("TravelMotivationScreen", () => {
  const completeOnboardingLocally = jest.fn();

  beforeEach(async () => {
    jest.clearAllMocks();
    // See InterestSelectScreen.test.tsx for why this must be an awaited
    // async act().
    await act(async () => {
      useOnboardingStore.getState().reset();
    });
    mockUseAuth.mockReturnValue({ completeOnboardingLocally });
  });

  it("selects a travel companion option", async () => {
    await render(<TravelMotivationScreen />);
    await waitFor(() => expect(screen.getByTestId("travel-companion-options")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("travel-companion-solo"));
    });

    expect(useOnboardingStore.getState().travelCompanion).toBe("solo");
  });

  it("updates the free-text motivation and shows a live character count", async () => {
    await render(<TravelMotivationScreen />);
    const input = screen.getByTestId("trip-motivation-input");

    await act(async () => {
      fireEvent.changeText(input, "Trying local street food");
    });

    expect(useOnboardingStore.getState().tripMotivation).toBe("Trying local street food");
    expect(screen.getByText("24/500")).toBeTruthy();
  });

  it("Continue navigates to OnboardingComplete without submitting anything", async () => {
    await render(<TravelMotivationScreen />);

    fireEvent.press(screen.getByTestId("travel-motivation-continue-button"));

    expect(mockNavigate).toHaveBeenCalledWith("OnboardingComplete");
    expect(mockSubmitOnboardingResponses).not.toHaveBeenCalled();
  });

  it("Skip submits the current answers, including companion and motivation", async () => {
    mockSubmitOnboardingResponses.mockResolvedValue({
      data: {
        onboarding_completed: true,
        onboarding_completed_at: "2026-01-01T00:00:00Z",
        interest_ids: [],
        travel_style: null,
        pace: null,
        budget_bracket: null,
        travel_companion: "solo",
        trip_motivation: "Trying local street food",
      },
      saved: true,
    });
    await render(<TravelMotivationScreen />);
    await waitFor(() => expect(screen.getByTestId("travel-companion-options")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("travel-companion-solo"));
    });
    await act(async () => {
      fireEvent.changeText(
        screen.getByTestId("trip-motivation-input"),
        "Trying local street food",
      );
    });

    await act(async () => {
      fireEvent.press(screen.getByTestId("onboarding-skip-link"));
    });

    expect(mockSubmitOnboardingResponses).toHaveBeenCalledWith(
      expect.objectContaining({
        travel_companion: "solo",
        trip_motivation: "Trying local street food",
      }),
    );
    await waitFor(() => expect(completeOnboardingLocally).toHaveBeenCalled());
  });
});
