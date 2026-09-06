import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { ApiError } from "../../api/client";
import { fetchInterests } from "../../api/onboarding";
import { createTrip, submitTripNotes } from "../../api/trips";
import { TripCreationScreen } from "../TripCreationScreen";

const mockReplace = jest.fn();
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => ({ replace: mockReplace, goBack: jest.fn() }),
}));

jest.mock("../../api/onboarding", () => ({
  fetchInterests: jest.fn(),
}));
jest.mock("../../api/trips", () => ({
  createTrip: jest.fn(),
  submitTripNotes: jest.fn(),
}));

jest.mock("../../i18n", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { en } = require("../../i18n/locales/en");
  const t = (key: string): unknown =>
    key.split(".").reduce((acc: unknown, part: string) => (acc as never)?.[part], en) ?? key;
  return { useTranslation: () => ({ t }) };
});

const mockFetchInterests = fetchInterests as jest.Mock;
const mockCreateTrip = createTrip as jest.Mock;
const mockSubmitTripNotes = submitTripNotes as jest.Mock;

describe("TripCreationScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockFetchInterests.mockResolvedValue([
      { id: 1, slug: "heritage", label: "Heritage" },
      { id: 2, slug: "food", label: "Food" },
    ]);
  });

  it("disables submit until title and destination are filled in", async () => {
    await render(<TripCreationScreen />);
    await waitFor(() => expect(screen.getByTestId("interest-chip-heritage")).toBeTruthy());

    const submit = screen.getByTestId("trip-submit-button");
    expect(submit.props.accessibilityState?.disabled).toBe(true);

    await act(async () => {
      fireEvent.changeText(screen.getByTestId("trip-title-input"), "Agra Weekend");
      fireEvent.changeText(screen.getByTestId("trip-destination-input"), "Agra, India");
    });

    expect(screen.getByTestId("trip-submit-button").props.accessibilityState?.disabled).toBe(
      false,
    );
  });

  it("creates the trip, submits notes, and navigates to Chat on success", async () => {
    mockCreateTrip.mockResolvedValue({ id: "trip-123" });
    mockSubmitTripNotes.mockResolvedValue({ id: "note-1" });

    await render(<TripCreationScreen />);
    await waitFor(() => expect(screen.getByTestId("interest-chip-heritage")).toBeTruthy());

    await act(async () => {
      fireEvent.changeText(screen.getByTestId("trip-title-input"), "Agra Weekend");
      fireEvent.changeText(screen.getByTestId("trip-destination-input"), "Agra, India");
      fireEvent.changeText(screen.getByTestId("trip-own-ideas-input"), "See the Taj at sunrise");
      fireEvent.press(screen.getByTestId("interest-chip-heritage"));
    });

    await act(async () => {
      fireEvent.press(screen.getByTestId("trip-submit-button"));
    });

    await waitFor(() => expect(mockReplace).toHaveBeenCalled());
    expect(mockCreateTrip).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Agra Weekend", destination: "Agra, India" }),
    );
    expect(mockSubmitTripNotes).toHaveBeenCalledWith("trip-123", "See the Taj at sunrise");
    expect(mockReplace).toHaveBeenCalledWith("Chat", {
      tripId: "trip-123",
      interests: ["heritage"],
      useOwnIdeas: true,
    });
  });

  it("shows a typed error message when trip creation fails", async () => {
    mockCreateTrip.mockRejectedValue(new ApiError(500, "Could not create trip"));

    await render(<TripCreationScreen />);
    await waitFor(() => expect(screen.getByTestId("interest-chip-heritage")).toBeTruthy());

    await act(async () => {
      fireEvent.changeText(screen.getByTestId("trip-title-input"), "Agra Weekend");
      fireEvent.changeText(screen.getByTestId("trip-destination-input"), "Agra, India");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("trip-submit-button"));
    });

    await waitFor(() => expect(screen.getByTestId("trip-creation-error")).toBeTruthy());
    expect(screen.getByText("Could not create trip")).toBeTruthy();
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
