import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import * as ImagePicker from "expo-image-picker";
import React from "react";

import { ApiError } from "../../api/client";
import { askPhotoQuestion } from "../../api/heritage";
import { PhotoQAScreen } from "../PhotoQAScreen";

const mockRoute = { params: { poiId: "poi-1", poiName: "Taj Mahal" } };
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useRoute: () => mockRoute,
}));

jest.mock("expo-image-picker", () => ({
  requestCameraPermissionsAsync: jest.fn(),
  requestMediaLibraryPermissionsAsync: jest.fn(),
  launchCameraAsync: jest.fn(),
  launchImageLibraryAsync: jest.fn(),
}));

jest.mock("../../api/heritage", () => ({
  askPhotoQuestion: jest.fn(),
}));

const mockAskPhotoQuestion = askPhotoQuestion as jest.Mock;
const mockRequestCamera = ImagePicker.requestCameraPermissionsAsync as jest.Mock;
const mockLaunchCamera = ImagePicker.launchCameraAsync as jest.Mock;

describe("PhotoQAScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("shows a permission-denied message without crashing when camera access is refused", async () => {
    mockRequestCamera.mockResolvedValue({ granted: false });

    await render(<PhotoQAScreen />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("capture-photo-button"));
    });

    await waitFor(() => expect(screen.getByTestId("photo-permission-error")).toBeTruthy());
  });

  it("captures a photo and asks a real grounded question", async () => {
    mockRequestCamera.mockResolvedValue({ granted: true });
    mockLaunchCamera.mockResolvedValue({
      canceled: false,
      assets: [{ uri: "file://photo.jpg" }],
    });
    mockAskPhotoQuestion.mockResolvedValue({
      poi_id: "poi-1",
      answer: "That's the main marble dome.",
      confidence: "high",
      grounded: true,
    });

    await render(<PhotoQAScreen />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("capture-photo-button"));
    });
    await waitFor(() => expect(screen.getByTestId("photo-preview")).toBeTruthy());

    await act(async () => {
      fireEvent.changeText(screen.getByTestId("photo-question-input"), "What is this dome?");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("ask-photo-question-button"));
    });

    await waitFor(() => expect(screen.getByTestId("photo-qa-result")).toBeTruthy());
    expect(screen.getByText("That's the main marble dome.")).toBeTruthy();
    expect(mockAskPhotoQuestion).toHaveBeenCalledWith(
      "poi-1",
      "What is this dome?",
      "file://photo.jpg",
    );
  });

  it("shows a typed error state when the question fails", async () => {
    mockRequestCamera.mockResolvedValue({ granted: true });
    mockLaunchCamera.mockResolvedValue({
      canceled: false,
      assets: [{ uri: "file://photo.jpg" }],
    });
    mockAskPhotoQuestion.mockRejectedValue(new ApiError(503, "Visual Q&A is unavailable."));

    await render(<PhotoQAScreen />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("capture-photo-button"));
    });
    await waitFor(() => expect(screen.getByTestId("photo-preview")).toBeTruthy());

    await act(async () => {
      fireEvent.changeText(screen.getByTestId("photo-question-input"), "What is this?");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("ask-photo-question-button"));
    });

    await waitFor(() => expect(screen.getByTestId("photo-qa-error")).toBeTruthy());
    expect(screen.getByText("Visual Q&A is unavailable.")).toBeTruthy();
  });

  it("disables Ask until both a photo and a question exist", async () => {
    await render(<PhotoQAScreen />);

    expect(
      screen.getByTestId("ask-photo-question-button").props.accessibilityState?.disabled,
    ).toBe(true);
  });
});
