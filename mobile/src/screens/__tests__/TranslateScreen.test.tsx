import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import * as ExpoAudio from "expo-audio";
import React from "react";

import { ApiError } from "../../api/client";
import { translateSpeech, translateText } from "../../api/translation";
import { TranslateScreen } from "../TranslateScreen";

jest.mock("../../api/translation", () => ({
  translateText: jest.fn(),
  translateSpeech: jest.fn(),
}));

const mockTranslateText = translateText as jest.Mock;
const mockTranslateSpeech = translateSpeech as jest.Mock;

const mockRecorder = { prepareToRecordAsync: jest.fn(), record: jest.fn(), stop: jest.fn(), uri: "file://clip.m4a" };
jest.mock("expo-audio", () => ({
  RecordingPresets: { HIGH_QUALITY: {} },
  requestRecordingPermissionsAsync: jest.fn(),
  useAudioRecorder: jest.fn(() => mockRecorder),
  useAudioRecorderState: jest.fn(() => ({ isRecording: false })),
}));

const mockRequestRecordingPermissions =
  ExpoAudio.requestRecordingPermissionsAsync as jest.Mock;
const mockUseAudioRecorderState = ExpoAudio.useAudioRecorderState as jest.Mock;

describe("TranslateScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAudioRecorderState.mockReturnValue({ isRecording: false });
  });

  it("translates an arbitrary typed phrase and shows script + transliteration", async () => {
    mockTranslateText.mockResolvedValue({
      original_text: "Where is the nearest railway station?",
      target_language: "Hindi",
      translated_text: "निकटतम रेलवे स्टेशन कहाँ है?",
      transliteration: "Nikatatam railway station kahaan hai?",
      note: null,
      recognized_language: true,
    });

    await render(<TranslateScreen />);

    await act(async () => {
      fireEvent.changeText(
        screen.getByTestId("translate-input"),
        "Where is the nearest railway station?",
      );
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("translate-button"));
    });

    await waitFor(() => expect(screen.getByTestId("translate-result")).toBeTruthy());
    expect(screen.getByText("निकटतम रेलवे स्टेशन कहाँ है?")).toBeTruthy();
    expect(screen.getByText("Nikatatam railway station kahaan hai?")).toBeTruthy();
    expect(mockTranslateText).toHaveBeenCalledWith(
      "Where is the nearest railway station?",
      "Hindi",
    );
  });

  it("switches target language when a different chip is selected", async () => {
    mockTranslateText.mockResolvedValue({
      original_text: "hello",
      target_language: "Telugu",
      translated_text: "నమస్కారం",
      transliteration: "Namaskaram",
      note: null,
      recognized_language: true,
    });

    await render(<TranslateScreen />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("language-chip-Telugu"));
      fireEvent.changeText(screen.getByTestId("translate-input"), "hello");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("translate-button"));
    });

    await waitFor(() => expect(mockTranslateText).toHaveBeenCalledWith("hello", "Telugu"));
  });

  it("shows a typed error state when translation fails", async () => {
    mockTranslateText.mockRejectedValue(
      new ApiError(503, "Translation is temporarily unavailable."),
    );

    await render(<TranslateScreen />);

    await act(async () => {
      fireEvent.changeText(screen.getByTestId("translate-input"), "hello");
    });
    await act(async () => {
      fireEvent.press(screen.getByTestId("translate-button"));
    });

    await waitFor(() => expect(screen.getByTestId("translate-error")).toBeTruthy());
    expect(screen.getByText("Translation is temporarily unavailable.")).toBeTruthy();
  });

  it("disables the translate button until a phrase is entered", async () => {
    await render(<TranslateScreen />);

    expect(screen.getByTestId("translate-button").props.accessibilityState?.disabled).toBe(true);
  });

  it("shows a permission error when microphone access is refused", async () => {
    mockRequestRecordingPermissions.mockResolvedValue({ granted: false });

    await render(<TranslateScreen />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("record-speech-button"));
    });

    await waitFor(() => expect(screen.getByTestId("record-permission-error")).toBeTruthy());
  });

  it("stops recording and translates the transcribed speech", async () => {
    mockUseAudioRecorderState.mockReturnValue({ isRecording: true });
    mockTranslateSpeech.mockResolvedValue({
      transcribed_text: "Where is the nearest railway station?",
      target_language: "Hindi",
      translated_text: "निकटतम रेलवे स्टेशन कहाँ है?",
      transliteration: "Nikatatam railway station kahaan hai?",
      note: null,
    });

    await render(<TranslateScreen />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("record-speech-button"));
    });

    await waitFor(() => expect(screen.getByTestId("translate-result")).toBeTruthy());
    expect(mockRecorder.stop).toHaveBeenCalled();
    expect(mockTranslateSpeech).toHaveBeenCalledWith("file://clip.m4a", "Hindi");
    expect(screen.getByText('Heard: “Where is the nearest railway station?”')).toBeTruthy();
    expect(screen.getByText("निकटतम रेलवे स्टेशन कहाँ है?")).toBeTruthy();
  });
});
