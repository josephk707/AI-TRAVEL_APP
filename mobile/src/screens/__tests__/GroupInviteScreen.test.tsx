import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { ApiError } from "../../api/client";
import {
  acceptInvite,
  createInvite,
  listTripMembers,
  reconcileItinerary,
  submitMemberPreferences,
} from "../../api/group";
import { fetchTrip } from "../../api/trips";
import { useAuth } from "../../auth/AuthContext";
import { GroupInviteScreen } from "../GroupInviteScreen";

jest.mock("react-native/Libraries/Share/Share", () => ({
  share: jest.fn().mockResolvedValue({ action: "sharedAction" }),
}));

jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useRoute: () => ({ params: { tripId: "trip-1" } }),
  useNavigation: () => ({ goBack: jest.fn() }),
}));

jest.mock("../../api/group", () => ({
  createInvite: jest.fn(),
  acceptInvite: jest.fn(),
  submitMemberPreferences: jest.fn(),
  listTripMembers: jest.fn(),
  reconcileItinerary: jest.fn(),
}));

jest.mock("../../api/trips", () => ({
  fetchTrip: jest.fn(),
}));

jest.mock("../../auth/AuthContext", () => ({
  useAuth: jest.fn(),
}));

const mockCreateInvite = createInvite as jest.Mock;
const mockAcceptInvite = acceptInvite as jest.Mock;
const mockSubmitMemberPreferences = submitMemberPreferences as jest.Mock;
const mockListTripMembers = listTripMembers as jest.Mock;
const mockReconcileItinerary = reconcileItinerary as jest.Mock;
const mockFetchTrip = fetchTrip as jest.Mock;
const mockUseAuth = useAuth as jest.Mock;

function makeMember(overrides: Record<string, unknown> = {}) {
  return {
    trip_id: "trip-1",
    user_id: "user-2",
    display_name: "Alex",
    role: "member",
    invite_status: "accepted",
    invited_at: "2026-01-01T00:00:00Z",
    responded_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("GroupInviteScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: { id: "user-1" } });
  });

  it("shows the member list and hides organiser-only actions for a regular member", async () => {
    mockListTripMembers.mockResolvedValue([makeMember()]);
    mockFetchTrip.mockResolvedValue({ owner_id: "someone-else" });

    await render(<GroupInviteScreen />);

    await waitFor(() => expect(screen.getByTestId("member-user-2")).toBeTruthy());
    expect(screen.queryByTestId("create-invite-button")).toBeNull();
    expect(screen.queryByTestId("reconcile-button")).toBeNull();
  });

  it("shows organiser-only actions for the trip owner", async () => {
    mockListTripMembers.mockResolvedValue([]);
    mockFetchTrip.mockResolvedValue({ owner_id: "user-1" });

    await render(<GroupInviteScreen />);

    await waitFor(() => expect(screen.getByTestId("create-invite-button")).toBeTruthy());
    expect(screen.getByTestId("reconcile-button")).toBeTruthy();
  });

  it("shows a typed error state with retry on failure", async () => {
    mockListTripMembers.mockRejectedValue(new ApiError(500, "Server exploded"));
    mockFetchTrip.mockResolvedValue({ owner_id: "user-1" });

    await render(<GroupInviteScreen />);

    await waitFor(() => expect(screen.getByTestId("group-error")).toBeTruthy());
    expect(screen.getByText("Server exploded")).toBeTruthy();
  });

  it("creates a real invite and displays the token", async () => {
    mockListTripMembers.mockResolvedValue([]);
    mockFetchTrip.mockResolvedValue({ owner_id: "user-1" });
    mockCreateInvite.mockResolvedValue({
      id: "invite-1",
      trip_id: "trip-1",
      method: "link",
      email: null,
      token: "abc123token",
      status: "pending",
      expires_at: "2026-02-01T00:00:00Z",
      invite_url: "aitouristguide://trips/invite/abc123token",
    });

    await render(<GroupInviteScreen />);
    await waitFor(() => expect(screen.getByTestId("create-invite-button")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("create-invite-button"));
    });

    await waitFor(() => expect(screen.getByTestId("invite-token-display")).toBeTruthy());
    expect(screen.getByText("abc123token")).toBeTruthy();
  });

  it("accepts a pasted invite token", async () => {
    mockListTripMembers.mockResolvedValue([]);
    mockFetchTrip.mockResolvedValue({ owner_id: "someone-else" });
    mockAcceptInvite.mockResolvedValue({ trip_id: "trip-1", role: "member", joined: true });

    await render(<GroupInviteScreen />);
    await waitFor(() => expect(screen.getByTestId("invite-token-input")).toBeTruthy());

    await act(async () => {
      fireEvent.changeText(screen.getByTestId("invite-token-input"), "some-token");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("accept-invite-button"));
    });

    await waitFor(() => expect(mockAcceptInvite).toHaveBeenCalledWith("some-token"));
  });

  it("saves the member's own preferences", async () => {
    mockListTripMembers.mockResolvedValue([]);
    mockFetchTrip.mockResolvedValue({ owner_id: "someone-else" });
    mockSubmitMemberPreferences.mockResolvedValue({
      trip_id: "trip-1",
      user_id: "user-1",
      interests: ["heritage", "food"],
      budget_max: 5000,
      constraints: {},
      submitted_at: "2026-01-01T00:00:00Z",
    });

    await render(<GroupInviteScreen />);
    await waitFor(() => expect(screen.getByTestId("preferences-interests-input")).toBeTruthy());

    await act(async () => {
      fireEvent.changeText(screen.getByTestId("preferences-interests-input"), "heritage, food");
    });
    await act(async () => {
      fireEvent.changeText(screen.getByTestId("preferences-budget-input"), "5000");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("save-preferences-button"));
    });

    await waitFor(() =>
      expect(mockSubmitMemberPreferences).toHaveBeenCalledWith(
        "trip-1",
        "user-1",
        ["heritage", "food"],
        5000,
      ),
    );
    expect(screen.getByText("Saved!")).toBeTruthy();
  });

  it("reconciles the group's plan and shows conflicts", async () => {
    mockListTripMembers.mockResolvedValue([]);
    mockFetchTrip.mockResolvedValue({ owner_id: "user-1" });
    mockReconcileItinerary.mockResolvedValue({
      trip_id: "trip-1",
      generation_status: "succeeded",
      summary: "A reconciled plan.",
      days: [],
      conflicts: [
        { field: "budget", description: "Members proposed different budgets.", resolution: "Used the lowest." },
      ],
      included_member_ids: ["user-1"],
      excluded_member_ids: [],
    });

    await render(<GroupInviteScreen />);
    await waitFor(() => expect(screen.getByTestId("reconcile-button")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("reconcile-button"));
    });

    await waitFor(() => expect(screen.getByTestId("conflict-0")).toBeTruthy());
    expect(screen.getByText("Used the lowest.")).toBeTruthy();
  });
});
