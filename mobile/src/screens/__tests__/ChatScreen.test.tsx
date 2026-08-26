import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { ApiError } from "../../api/client";
import {
  fetchTrip,
  generateItinerary,
  modifyItinerary,
  updateTrip,
  Trip,
} from "../../api/trips";
import { ChatScreen } from "../ChatScreen";

const mockNavigate = jest.fn();
const mockNavigation = { navigate: mockNavigate };
const mockRoute = {
  params: { tripId: "trip-1", interests: ["heritage"], useOwnIdeas: false },
};
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => mockNavigation,
  useRoute: () => mockRoute,
}));

jest.mock("../../api/trips", () => ({
  fetchTrip: jest.fn(),
  generateItinerary: jest.fn(),
  modifyItinerary: jest.fn(),
  updateTrip: jest.fn(),
}));

const mockFetchTrip = fetchTrip as jest.Mock;
const mockGenerateItinerary = generateItinerary as jest.Mock;
const mockModifyItinerary = modifyItinerary as jest.Mock;
const mockUpdateTrip = updateTrip as jest.Mock;

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
    generation_status: "none",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("ChatScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("auto-generates the itinerary on first entry and shows the AI summary", async () => {
    mockFetchTrip.mockResolvedValue(makeTrip({ generation_status: "none" }));
    mockGenerateItinerary.mockResolvedValue({
      trip_id: "trip-1",
      generation_status: "succeeded",
      summary: "A lovely Agra day trip.",
      days: [],
      budget_summary: { estimated_total: 1000, planned_budget: 15000, over_budget: false, tolerance_pct: 10 },
      conflicts: [],
      degraded: false,
      degradedMessage: null,
    });

    await render(<ChatScreen />);

    await waitFor(() => expect(screen.getByText("A lovely Agra day trip.")).toBeTruthy());
    expect(mockGenerateItinerary).toHaveBeenCalledWith(
      "trip-1",
      expect.objectContaining({ interests: ["heritage"] }),
    );
    expect(screen.getByTestId("view-itinerary-link")).toBeTruthy();
  });

  it("shows a clarification panel when the backend asks for more details", async () => {
    mockFetchTrip.mockResolvedValue(makeTrip({ generation_status: "none" }));
    mockGenerateItinerary.mockRejectedValueOnce(
      new ApiError(422, "What's your rough budget for this trip?", "CLARIFICATION_NEEDED", {
        missing_fields: ["budget"],
      }),
    );

    await render(<ChatScreen />);

    await waitFor(() => expect(screen.getByTestId("clarification-panel")).toBeTruthy());
    expect(screen.getByText("What's your rough budget for this trip?")).toBeTruthy();
    expect(screen.getByTestId("clarify-budget-input")).toBeTruthy();
  });

  it("retries generation with the provided budget after clarification", async () => {
    mockFetchTrip.mockResolvedValue(makeTrip({ generation_status: "none" }));
    mockGenerateItinerary
      .mockRejectedValueOnce(
        new ApiError(422, "What's your rough budget?", "CLARIFICATION_NEEDED", {
          missing_fields: ["budget"],
        }),
      )
      .mockResolvedValueOnce({
        trip_id: "trip-1",
        generation_status: "succeeded",
        summary: "Here you go.",
        days: [],
        budget_summary: null,
        conflicts: [],
        degraded: false,
        degradedMessage: null,
      });
    mockUpdateTrip.mockResolvedValue(makeTrip());

    await render(<ChatScreen />);
    await waitFor(() => expect(screen.getByTestId("clarification-panel")).toBeTruthy());

    await act(async () => {
      fireEvent.changeText(screen.getByTestId("clarify-budget-input"), "15000");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("clarify-submit-button"));
    });

    await waitFor(() => expect(screen.getByText("Here you go.")).toBeTruthy());
    expect(mockGenerateItinerary).toHaveBeenCalledTimes(2);
  });

  it("welcomes back a returning user and sends a modification request", async () => {
    mockFetchTrip.mockResolvedValue(makeTrip({ generation_status: "succeeded" }));
    mockModifyItinerary.mockResolvedValue({
      reply: "Sure — pushed it to 8am.",
      changed_item_ids: ["item-1"],
      days: [],
    });

    await render(<ChatScreen />);

    await waitFor(() =>
      expect(screen.getByText("Welcome back! Ask me for any changes to your plan.")).toBeTruthy(),
    );

    await act(async () => {
      fireEvent.changeText(screen.getByTestId("chat-composer-input"), "start it at 8am");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("chat-send-button"));
    });

    await waitFor(() => expect(screen.getByText("Sure — pushed it to 8am.")).toBeTruthy());
    expect(mockModifyItinerary).toHaveBeenCalledWith("trip-1", "start it at 8am");
  });

  it("navigates to ItineraryView when the view-itinerary link is pressed", async () => {
    mockFetchTrip.mockResolvedValue(makeTrip({ generation_status: "succeeded" }));

    await render(<ChatScreen />);
    await waitFor(() => expect(screen.getByTestId("view-itinerary-link")).toBeTruthy());

    fireEvent.press(screen.getByTestId("view-itinerary-link"));

    expect(mockNavigate).toHaveBeenCalledWith("ItineraryView", { tripId: "trip-1" });
  });
});
