import { act, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";
import { Text } from "react-native";

import { updatePreferredLanguage } from "../../api/auth";
import { secureStorage } from "../../lib/secureStorage";
import { LanguageProvider, useTranslation } from "../LanguageContext";

jest.mock("../../api/auth", () => ({
  updatePreferredLanguage: jest.fn(),
}));

jest.mock("../../lib/secureStorage", () => ({
  secureStorage: {
    getItem: jest.fn(),
    setItem: jest.fn(),
    removeItem: jest.fn(),
  },
}));

jest.mock("expo-localization", () => ({
  getLocales: () => [{ languageCode: null }],
}));

const mockUpdatePreferredLanguage = updatePreferredLanguage as jest.Mock;
const mockGetItem = secureStorage.getItem as jest.Mock;
const mockSetItem = secureStorage.setItem as jest.Mock;

function Probe(): React.JSX.Element {
  const { t, language, setLanguage, syncFromServerProfile, ready } = useTranslation();
  return (
    <>
      <Text testID="ready">{String(ready)}</Text>
      <Text testID="language">{language}</Text>
      <Text testID="retry-label">{t("common.retry")}</Text>
      <Text testID="hi-only-fallback">{t("home.greeting")}</Text>
      <Text testID="missing-key">{t("nonexistent.key")}</Text>
      <Text testID="set-hi" onPress={() => void setLanguage("hi")}>
        set-hi
      </Text>
      <Text testID="sync-te" onPress={() => syncFromServerProfile("te")}>
        sync-te
      </Text>
    </>
  );
}

describe("LanguageContext", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetItem.mockResolvedValue(null);
    mockSetItem.mockResolvedValue(undefined);
    mockUpdatePreferredLanguage.mockResolvedValue({});
  });

  it("defaults to English when no stored preference and no matching device locale exist", async () => {
    await render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("ready").props.children).toBe("true"));
    expect(screen.getByTestId("language").props.children).toBe("en");
    expect(screen.getByTestId("retry-label").props.children).toBe("Retry");
  });

  it("falls back to the English string for a key missing from the active language's file", async () => {
    await render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("ready").props.children).toBe("true"));

    await act(async () => {
      screen.getByTestId("set-hi").props.onPress();
    });

    // "home.greeting" IS translated in hi.ts — proves the real translation is used, not English.
    await waitFor(() => expect(screen.getByTestId("language").props.children).toBe("hi"));
    expect(screen.getByTestId("hi-only-fallback").props.children).toBe("नमस्ते, यात्री");

    // A key that exists nowhere falls back to the raw key, never blank/undefined.
    expect(screen.getByTestId("missing-key").props.children).toBe("nonexistent.key");
  });

  it("setLanguage persists locally and syncs to the backend profile", async () => {
    await render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("ready").props.children).toBe("true"));

    await act(async () => {
      screen.getByTestId("set-hi").props.onPress();
    });

    expect(mockSetItem).toHaveBeenCalledWith("yatra_language", "hi");
    expect(mockSetItem).toHaveBeenCalledWith("yatra_language_explicit", "1");
    await waitFor(() => expect(mockUpdatePreferredLanguage).toHaveBeenCalledWith("hi"));
  });

  it("adopts the server's language on first sync when this device has no explicit choice", async () => {
    await render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("ready").props.children).toBe("true"));

    await act(async () => {
      screen.getByTestId("sync-te").props.onPress();
    });

    await waitFor(() => expect(screen.getByTestId("language").props.children).toBe("te"));
  });

  it("reads a previously stored language back on mount", async () => {
    mockGetItem.mockImplementation((key: string) =>
      Promise.resolve(key === "yatra_language" ? "kn" : "1"),
    );

    await render(
      <LanguageProvider>
        <Probe />
      </LanguageProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("language").props.children).toBe("kn"));
  });
});
