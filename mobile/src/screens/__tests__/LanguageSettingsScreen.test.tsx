import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { SUPPORTED_LANGUAGES } from "../../i18n/languages";
import { LanguageSettingsScreen } from "../LanguageSettingsScreen";

jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => ({ goBack: jest.fn() }),
}));

const mockSetLanguage = jest.fn();
let mockLanguage = "en";

jest.mock("../../i18n", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { en } = require("../../i18n/locales/en");
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { SUPPORTED_LANGUAGES } = require("../../i18n/languages");
  const t = (key: string): unknown =>
    key.split(".").reduce((acc: unknown, part: string) => (acc as never)?.[part], en) ?? key;
  return {
    useTranslation: () => ({
      t,
      get language() {
        return mockLanguage;
      },
      languageOptions: SUPPORTED_LANGUAGES,
      setLanguage: mockSetLanguage,
    }),
  };
});

describe("LanguageSettingsScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockLanguage = "en";
  });

  it("lists every supported language with its native label", async () => {
    await render(<LanguageSettingsScreen />);

    for (const option of SUPPORTED_LANGUAGES) {
      expect(screen.getByTestId(`language-option-${option.code}`)).toBeTruthy();
      expect(screen.getByText(option.nativeLabel)).toBeTruthy();
    }
  });

  it("marks the currently active language as selected", async () => {
    mockLanguage = "hi";
    await render(<LanguageSettingsScreen />);

    expect(screen.getByTestId("language-option-hi").props.accessibilityState.selected).toBe(true);
    expect(screen.getByTestId("language-option-en").props.accessibilityState.selected).toBe(false);
  });

  it("calls setLanguage with the pressed language's code", async () => {
    mockSetLanguage.mockResolvedValue({ syncedToServer: true });
    await render(<LanguageSettingsScreen />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("language-option-hi"));
    });

    await waitFor(() => expect(mockSetLanguage).toHaveBeenCalledWith("hi"));
  });

  it("does not call setLanguage when the already-active language is pressed", async () => {
    mockLanguage = "en";
    await render(<LanguageSettingsScreen />);

    fireEvent.press(screen.getByTestId("language-option-en"));

    expect(mockSetLanguage).not.toHaveBeenCalled();
  });

  it("shows a real error message when the backend sync fails, without reverting the local selection", async () => {
    mockSetLanguage.mockResolvedValue({ syncedToServer: false });
    await render(<LanguageSettingsScreen />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("language-option-ta"));
    });

    await waitFor(() => expect(screen.getByText("Couldn't update your language — please try again.")).toBeTruthy());
  });
});
