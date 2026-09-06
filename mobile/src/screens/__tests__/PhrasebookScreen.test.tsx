import { render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { ApiError } from "../../api/client";
import { downloadTripPhrasebook } from "../../api/phrasebook";
import { PhrasebookScreen } from "../PhrasebookScreen";

jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useRoute: () => ({ params: { tripId: "trip-1" } }),
  useNavigation: () => ({ goBack: jest.fn() }),
}));

jest.mock("../../i18n", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { en } = require("../../i18n/locales/en");
  const t = (key: string): unknown =>
    key.split(".").reduce((acc: unknown, part: string) => (acc as never)?.[part], en) ?? key;
  return { useTranslation: () => ({ t }) };
});

jest.mock("../../api/phrasebook", () => ({
  downloadTripPhrasebook: jest.fn(),
}));

const mockDownloadTripPhrasebook = downloadTripPhrasebook as jest.Mock;

function makeEntry(overrides: Record<string, unknown> = {}) {
  return {
    id: "entry-1",
    region: "Agra",
    language_code: "hi-IN",
    category: "courtesy",
    phrase_en: "Hello",
    phrase_local_script: "नमस्ते",
    phrase_transliteration: "Namaste",
    audio_url: null,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("PhrasebookScreen", () => {
  beforeEach(() => jest.clearAllMocks());

  it("shows an empty state when no phrases are available", async () => {
    mockDownloadTripPhrasebook.mockResolvedValue([]);

    await render(<PhrasebookScreen />);

    await waitFor(() => expect(screen.getByTestId("phrasebook-empty")).toBeTruthy());
  });

  it("renders real curated phrases grouped by category", async () => {
    mockDownloadTripPhrasebook.mockResolvedValue([makeEntry()]);

    await render(<PhrasebookScreen />);

    await waitFor(() => expect(screen.getByTestId("phrase-entry-1")).toBeTruthy());
    expect(screen.getByText("Hello")).toBeTruthy();
    expect(screen.getByText("नमस्ते")).toBeTruthy();
    expect(screen.getByText("Namaste")).toBeTruthy();
  });

  it("shows a typed error state with retry on failure", async () => {
    mockDownloadTripPhrasebook.mockRejectedValue(new ApiError(500, "Server exploded"));

    await render(<PhrasebookScreen />);

    await waitFor(() => expect(screen.getByTestId("phrasebook-error")).toBeTruthy());
    expect(screen.getByText("Server exploded")).toBeTruthy();
  });
});
