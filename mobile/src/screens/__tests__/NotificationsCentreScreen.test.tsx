import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { ApiError } from "../../api/client";
import { listNotifications, markNotificationRead } from "../../api/notifications";
import { NotificationsCentreScreen } from "../NotificationsCentreScreen";

jest.mock("../../api/notifications", () => ({
  listNotifications: jest.fn(),
  markNotificationRead: jest.fn(),
}));

jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => ({ goBack: jest.fn() }),
}));

const mockListNotifications = listNotifications as jest.Mock;
const mockMarkNotificationRead = markNotificationRead as jest.Mock;

function makeNotification(overrides: Record<string, unknown> = {}) {
  return {
    id: "notif-1",
    user_id: "user-1",
    trip_id: null,
    type: "arrival",
    title: "You've arrived!",
    body: "Welcome to the Taj Mahal.",
    payload: {},
    read_at: null,
    delivered_channels: ["in_app"],
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("NotificationsCentreScreen", () => {
  beforeEach(() => jest.clearAllMocks());

  it("shows an empty state when there are no notifications", async () => {
    mockListNotifications.mockResolvedValue([]);

    await render(<NotificationsCentreScreen />);

    await waitFor(() => expect(screen.getByTestId("notifications-empty")).toBeTruthy());
  });

  it("renders real notifications returned by the backend", async () => {
    mockListNotifications.mockResolvedValue([makeNotification()]);

    await render(<NotificationsCentreScreen />);

    await waitFor(() => expect(screen.getByTestId("notification-notif-1")).toBeTruthy());
    expect(screen.getByText("You've arrived!")).toBeTruthy();
    expect(screen.getByTestId("unread-dot-notif-1")).toBeTruthy();
  });

  it("shows a typed error state with retry on failure", async () => {
    mockListNotifications.mockRejectedValue(new ApiError(500, "Server exploded"));

    await render(<NotificationsCentreScreen />);

    await waitFor(() => expect(screen.getByTestId("notifications-error")).toBeTruthy());
    expect(screen.getByText("Server exploded")).toBeTruthy();
  });

  it("marks a notification read on press and clears the unread dot", async () => {
    mockListNotifications.mockResolvedValue([makeNotification()]);
    mockMarkNotificationRead.mockResolvedValue(makeNotification({ read_at: "2026-01-02T00:00:00Z" }));

    await render(<NotificationsCentreScreen />);
    await waitFor(() => expect(screen.getByTestId("notification-notif-1")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("notification-notif-1"));
    });

    await waitFor(() => expect(mockMarkNotificationRead).toHaveBeenCalledWith("notif-1"));
    expect(screen.queryByTestId("unread-dot-notif-1")).toBeNull();
  });
});
