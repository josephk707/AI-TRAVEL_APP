import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { useAuth } from "../../auth/AuthContext";
import { secureStorage } from "../../lib/secureStorage";
import { ThemeProvider } from "../../theme";
import { SettingsScreen } from "../SettingsScreen";

jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => ({ navigate: jest.fn(), goBack: jest.fn() }),
}));

jest.mock("../../auth/AuthContext", () => ({
  useAuth: jest.fn(),
}));

jest.mock("../../i18n", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { en } = require("../../i18n/locales/en");
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { SUPPORTED_LANGUAGES } = require("../../i18n/languages");
  const t = (key: string): unknown =>
    key.split(".").reduce((acc: unknown, part: string) => (acc as never)?.[part], en) ?? key;
  return {
    useTranslation: () => ({ t, language: "en" }),
    SUPPORTED_LANGUAGES,
  };
});

jest.mock("../../lib/secureStorage", () => {
  const store = new Map<string, string>();
  return {
    secureStorage: {
      getItem: jest.fn((key: string) => Promise.resolve(store.get(key) ?? null)),
      setItem: jest.fn((key: string, value: string) => {
        store.set(key, value);
        return Promise.resolve();
      }),
      removeItem: jest.fn(),
      __store: store,
    },
  };
});

const mockUseAuth = useAuth as jest.Mock;
const mockStorage = secureStorage as unknown as { setItem: jest.Mock; __store: Map<string, string> };

describe("SettingsScreen — appearance", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockStorage.__store.clear();
    mockUseAuth.mockReturnValue({ signOut: jest.fn() });
  });

  it("renders the three appearance options with System selected by default", async () => {
    await render(
      <ThemeProvider>
        <SettingsScreen />
      </ThemeProvider>,
    );

    expect(screen.getByText("Appearance")).toBeTruthy();
    expect(screen.getByTestId("settings-appearance-system").props.accessibilityState.selected).toBe(true);
    expect(screen.getByTestId("settings-appearance-light").props.accessibilityState.selected).toBe(false);
    expect(screen.getByTestId("settings-appearance-dark").props.accessibilityState.selected).toBe(false);
  });

  it("selecting Dark updates the selection and persists the preference", async () => {
    await render(
      <ThemeProvider>
        <SettingsScreen />
      </ThemeProvider>,
    );

    await act(async () => {
      fireEvent.press(screen.getByTestId("settings-appearance-dark"));
    });

    await waitFor(() =>
      expect(screen.getByTestId("settings-appearance-dark").props.accessibilityState.selected).toBe(true),
    );
    expect(mockStorage.setItem).toHaveBeenCalledWith("yatra_theme_mode", "dark");
  });

  it("restores a previously persisted preference on mount", async () => {
    mockStorage.__store.set("yatra_theme_mode", "light");

    await render(
      <ThemeProvider>
        <SettingsScreen />
      </ThemeProvider>,
    );

    await waitFor(() =>
      expect(screen.getByTestId("settings-appearance-light").props.accessibilityState.selected).toBe(true),
    );
  });
});
