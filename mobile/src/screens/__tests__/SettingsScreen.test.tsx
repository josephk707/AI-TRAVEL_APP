import { fireEvent, render, screen } from "@testing-library/react-native";
import React from "react";

import { useAuth } from "../../auth/AuthContext";
import { SettingsScreen } from "../SettingsScreen";

const mockNavigate = jest.fn();
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => ({ navigate: mockNavigate, goBack: jest.fn() }),
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
    useTranslation: () => ({ t, language: "hi" }),
    SUPPORTED_LANGUAGES,
  };
});

const mockUseAuth = useAuth as jest.Mock;

describe("SettingsScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockUseAuth.mockReturnValue({ signOut: jest.fn() });
  });

  it("shows the current language's native label next to the Language row", async () => {
    await render(<SettingsScreen />);

    expect(screen.getByText("हिन्दी")).toBeTruthy();
  });

  it("navigates to LanguageSettings when the Language row is pressed", async () => {
    await render(<SettingsScreen />);

    fireEvent.press(screen.getByTestId("settings-row-Language"));

    expect(mockNavigate).toHaveBeenCalledWith("LanguageSettings");
  });

  it("navigates to Notifications when the Notifications row is pressed", async () => {
    await render(<SettingsScreen />);

    fireEvent.press(screen.getByTestId("settings-row-Notifications"));

    expect(mockNavigate).toHaveBeenCalledWith("Notifications");
  });

  it("calls the real signOut() when the sign-out button is pressed", async () => {
    const signOut = jest.fn();
    mockUseAuth.mockReturnValue({ signOut });
    await render(<SettingsScreen />);

    fireEvent.press(screen.getByTestId("settings-sign-out-button"));

    expect(signOut).toHaveBeenCalled();
  });
});
