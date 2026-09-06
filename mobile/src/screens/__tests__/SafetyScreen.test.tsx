import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";
import { Alert } from "react-native";

import { ApiError } from "../../api/client";
import {
  addTrustedContact,
  listTrustedContacts,
  startLocationShare,
  stopLocationShare,
  triggerSos,
} from "../../api/safety";
import { SafetyScreen } from "../SafetyScreen";

jest.mock("react-native/Libraries/Share/Share", () => ({
  share: jest.fn().mockResolvedValue({ action: "sharedAction" }),
}));

jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useRoute: () => ({ params: { tripId: "trip-1" } }),
  useNavigation: () => ({ goBack: jest.fn() }),
}));

jest.mock("../../api/safety", () => ({
  addTrustedContact: jest.fn(),
  listTrustedContacts: jest.fn(),
  startLocationShare: jest.fn(),
  stopLocationShare: jest.fn(),
  triggerSos: jest.fn(),
}));

const mockAddTrustedContact = addTrustedContact as jest.Mock;
const mockListTrustedContacts = listTrustedContacts as jest.Mock;
const mockStartLocationShare = startLocationShare as jest.Mock;
const mockStopLocationShare = stopLocationShare as jest.Mock;
const mockTriggerSos = triggerSos as jest.Mock;

describe("SafetyScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Alert, "alert").mockImplementation((_title, _message, buttons) => {
      const confirm = buttons?.find((b) => b.text?.includes("Send"));
      confirm?.onPress?.();
    });
  });

  it("shows an empty state when there are no trusted contacts", async () => {
    mockListTrustedContacts.mockResolvedValue([]);

    await render(<SafetyScreen />);

    await waitFor(() => expect(screen.getByTestId("contacts-empty")).toBeTruthy());
  });

  it("renders real trusted contacts returned by the backend", async () => {
    mockListTrustedContacts.mockResolvedValue([
      { id: "c1", user_id: "user-1", name: "Mom", phone: "+911234567890", email: null, created_at: "2026-01-01T00:00:00Z" },
    ]);

    await render(<SafetyScreen />);

    await waitFor(() => expect(screen.getByTestId("contact-c1")).toBeTruthy());
    expect(screen.getByText("Mom")).toBeTruthy();
  });

  it("shows a typed error state with retry on failure", async () => {
    mockListTrustedContacts.mockRejectedValue(new ApiError(500, "Server exploded"));

    await render(<SafetyScreen />);

    await waitFor(() => expect(screen.getByTestId("safety-error")).toBeTruthy());
    expect(screen.getByText("Server exploded")).toBeTruthy();
  });

  it("adds a new trusted contact", async () => {
    mockListTrustedContacts.mockResolvedValue([]);
    mockAddTrustedContact.mockResolvedValue({
      id: "c2",
      user_id: "user-1",
      name: "Dad",
      phone: "+919999999999",
      email: null,
      created_at: "2026-01-01T00:00:00Z",
    });

    await render(<SafetyScreen />);
    await waitFor(() => expect(screen.getByTestId("contact-name-input")).toBeTruthy());

    await act(async () => {
      fireEvent.changeText(screen.getByTestId("contact-name-input"), "Dad");
    });
    await act(async () => {
      fireEvent.changeText(screen.getByTestId("contact-phone-input"), "+919999999999");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("add-contact-button"));
    });

    await waitFor(() =>
      expect(mockAddTrustedContact).toHaveBeenCalledWith("Dad", "+919999999999"),
    );
  });

  it("starts and stops real location sharing", async () => {
    mockListTrustedContacts.mockResolvedValue([]);
    mockStartLocationShare.mockResolvedValue({
      id: "share-1",
      trip_id: "trip-1",
      share_token: "tok123",
      is_active: true,
      started_at: "2026-01-01T00:00:00Z",
      expires_at: "2026-01-08T00:00:00Z",
      share_url: "aitouristguide://share/tok123",
    });
    mockStopLocationShare.mockResolvedValue(undefined);

    await render(<SafetyScreen />);
    await waitFor(() => expect(screen.getByTestId("start-share-button")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("start-share-button"));
    });

    await waitFor(() => expect(screen.getByTestId("share-url-display")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("stop-share-button"));
    });

    await waitFor(() => expect(mockStopLocationShare).toHaveBeenCalledWith("trip-1"));
  });

  it("sends a real SOS alert after confirmation", async () => {
    mockListTrustedContacts.mockResolvedValue([]);
    mockTriggerSos.mockResolvedValue({
      id: "sos-1",
      triggered_at: "2026-01-01T00:00:00Z",
      last_known_lat: null,
      last_known_lng: null,
      location_captured_at: null,
      contacts_notified: 1,
    });

    await render(<SafetyScreen />);
    await waitFor(() => expect(screen.getByTestId("sos-button")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("sos-button"));
    });

    await waitFor(() => expect(mockTriggerSos).toHaveBeenCalledWith("trip-1"));
    await waitFor(() => expect(screen.getByTestId("sos-sent-text")).toBeTruthy());
  });
});
