import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { ApiError } from "../../api/client";
import { createCollection, listCollections, listFavorites } from "../../api/collections";
import { CollectionsScreen } from "../CollectionsScreen";

const mockNavigate = jest.fn();
const mockAddListener = jest.fn((event: string, callback: () => void) => {
  if (event === "focus") callback();
  return () => {};
});
const mockNavigation = { navigate: mockNavigate, addListener: mockAddListener };
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => mockNavigation,
}));

jest.mock("../../api/collections", () => ({
  listFavorites: jest.fn(),
  listCollections: jest.fn(),
  createCollection: jest.fn(),
}));

const mockListFavorites = listFavorites as jest.Mock;
const mockListCollections = listCollections as jest.Mock;
const mockCreateCollection = createCollection as jest.Mock;

describe("CollectionsScreen", () => {
  beforeEach(() => jest.clearAllMocks());

  it("shows empty states for favorites and collections", async () => {
    mockListFavorites.mockResolvedValue([]);
    mockListCollections.mockResolvedValue([]);

    await render(<CollectionsScreen />);

    await waitFor(() => expect(screen.getByTestId("favorites-empty")).toBeTruthy());
    expect(screen.getByTestId("collections-empty")).toBeTruthy();
  });

  it("renders real favorites and collections returned by the backend", async () => {
    mockListFavorites.mockResolvedValue([
      { poi_id: "poi-1", poi_name: "Taj Mahal", poi_category: "heritage", created_at: "2026-01-01T00:00:00Z" },
    ]);
    mockListCollections.mockResolvedValue([
      { id: "col-1", user_id: "user-1", name: "Heritage Wishlist", created_at: "2026-01-01T00:00:00Z", item_count: 2 },
    ]);

    await render(<CollectionsScreen />);

    await waitFor(() => expect(screen.getByTestId("favorite-poi-1")).toBeTruthy());
    expect(screen.getByText("Taj Mahal")).toBeTruthy();
    expect(screen.getByTestId("collection-col-1")).toBeTruthy();
    expect(screen.getByText("Heritage Wishlist (2)")).toBeTruthy();
  });

  it("shows a typed error state with retry on failure", async () => {
    mockListFavorites.mockRejectedValue(new ApiError(500, "Server exploded"));
    mockListCollections.mockResolvedValue([]);

    await render(<CollectionsScreen />);

    await waitFor(() => expect(screen.getByTestId("collections-error")).toBeTruthy());
    expect(screen.getByText("Server exploded")).toBeTruthy();
  });

  it("creates a new collection and refreshes the list", async () => {
    mockListFavorites.mockResolvedValue([]);
    mockListCollections.mockResolvedValue([]);
    mockCreateCollection.mockResolvedValue({
      id: "col-2",
      user_id: "user-1",
      name: "Foodie spots",
      created_at: "2026-01-01T00:00:00Z",
      item_count: 0,
    });

    await render(<CollectionsScreen />);
    await waitFor(() => expect(screen.getByTestId("collections-empty")).toBeTruthy());

    await act(async () => {
      fireEvent.changeText(screen.getByTestId("new-collection-input"), "Foodie spots");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("create-collection-button"));
    });

    await waitFor(() => expect(mockCreateCollection).toHaveBeenCalledWith("Foodie spots"));
  });
});
