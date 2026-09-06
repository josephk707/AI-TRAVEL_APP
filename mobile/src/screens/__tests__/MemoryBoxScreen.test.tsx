import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import * as ImagePicker from "expo-image-picker";
import React from "react";
import { Alert } from "react-native";

import { useAuth } from "../../auth/AuthContext";
import { ApiError } from "../../api/client";
import { createMemoryItem, deleteMemoryItem, listMemoryItems } from "../../api/memory";
import { MemoryBoxScreen } from "../MemoryBoxScreen";

jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useRoute: () => ({ params: { tripId: "trip-1" } }),
  useNavigation: () => ({ goBack: jest.fn() }),
}));

jest.mock("../../auth/AuthContext", () => ({
  useAuth: jest.fn(),
}));

jest.mock("../../api/memory", () => ({
  createMemoryItem: jest.fn(),
  listMemoryItems: jest.fn(),
  deleteMemoryItem: jest.fn(),
}));

jest.mock("expo-image-picker", () => ({
  requestMediaLibraryPermissionsAsync: jest.fn(),
  launchImageLibraryAsync: jest.fn(),
}));

jest.mock("../../lib/supabase", () => ({
  supabase: {
    storage: {
      from: jest.fn(() => ({
        upload: jest.fn().mockResolvedValue({ error: null }),
        remove: jest.fn().mockResolvedValue({ error: null }),
      })),
    },
  },
}));

const mockUseAuth = useAuth as jest.Mock;
const mockListMemoryItems = listMemoryItems as jest.Mock;
const mockCreateMemoryItem = createMemoryItem as jest.Mock;
const mockDeleteMemoryItem = deleteMemoryItem as jest.Mock;
const mockRequestMediaLibrary = ImagePicker.requestMediaLibraryPermissionsAsync as jest.Mock;

function makeItem(overrides: Record<string, unknown> = {}) {
  return {
    id: "item-1",
    trip_id: "trip-1",
    user_id: "user-1",
    item_type: "note",
    storage_path: null,
    caption: "Sunrise at the Taj was unforgettable.",
    taken_at: null,
    uploaded_at: "2026-01-01T00:00:00Z",
    retention_expires_at: "2027-01-01T00:00:00Z",
    expiry_reminder_sent_at: null,
    downloaded_at: null,
    ...overrides,
  };
}

describe("MemoryBoxScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: { id: "user-1" } });
  });

  it("shows an empty state when there are no memories yet", async () => {
    mockListMemoryItems.mockResolvedValue([]);

    await render(<MemoryBoxScreen />);

    await waitFor(() => expect(screen.getByTestId("memory-empty")).toBeTruthy());
  });

  it("renders real saved memories returned by the backend", async () => {
    mockListMemoryItems.mockResolvedValue([makeItem()]);

    await render(<MemoryBoxScreen />);

    await waitFor(() => expect(screen.getByTestId("memory-item-item-1")).toBeTruthy());
    expect(screen.getByText("Sunrise at the Taj was unforgettable.")).toBeTruthy();
  });

  it("shows a typed error state with retry on failure", async () => {
    mockListMemoryItems.mockRejectedValue(new ApiError(500, "Server exploded"));

    await render(<MemoryBoxScreen />);

    await waitFor(() => expect(screen.getByTestId("memory-error")).toBeTruthy());
    expect(screen.getByText("Server exploded")).toBeTruthy();
  });

  it("saves a text note and refreshes the list", async () => {
    mockListMemoryItems.mockResolvedValue([]);
    mockCreateMemoryItem.mockResolvedValue(makeItem());

    await render(<MemoryBoxScreen />);
    await waitFor(() => expect(screen.getByTestId("memory-empty")).toBeTruthy());

    await act(async () => {
      fireEvent.changeText(screen.getByTestId("memory-note-input"), "A great day");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("memory-save-note-button"));
    });

    await waitFor(() =>
      expect(mockCreateMemoryItem).toHaveBeenCalledWith("trip-1", {
        item_type: "note",
        caption: "A great day",
      }),
    );
  });

  it("shows a permission error when photo library access is denied", async () => {
    mockListMemoryItems.mockResolvedValue([]);
    mockRequestMediaLibrary.mockResolvedValue({ granted: false });

    await render(<MemoryBoxScreen />);
    await waitFor(() => expect(screen.getByTestId("memory-empty")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("memory-add-photo-button"));
    });

    await waitFor(() => expect(screen.getByTestId("memory-upload-error")).toBeTruthy());
  });

  it("deletes a memory item on confirmation", async () => {
    mockListMemoryItems.mockResolvedValue([makeItem()]);
    mockDeleteMemoryItem.mockResolvedValue(undefined);
    jest.spyOn(Alert, "alert").mockImplementation((_title, _msg, buttons) => {
      const destructive = buttons?.find((b) => b.style === "destructive");
      destructive?.onPress?.();
    });

    await render(<MemoryBoxScreen />);
    await waitFor(() => expect(screen.getByTestId("memory-item-item-1")).toBeTruthy());

    await act(async () => {
      fireEvent.press(screen.getByTestId("memory-delete-item-1"));
    });

    await waitFor(() => expect(mockDeleteMemoryItem).toHaveBeenCalledWith("trip-1", "item-1"));
  });
});
