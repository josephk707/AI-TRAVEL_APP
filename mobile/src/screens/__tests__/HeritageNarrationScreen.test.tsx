import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import React from "react";

import { ApiError } from "../../api/client";
import { fetchNarration } from "../../api/heritage";
import { HeritageNarrationScreen } from "../HeritageNarrationScreen";

const mockNavigate = jest.fn();
const mockNavigation = { navigate: mockNavigate, goBack: jest.fn() };
const mockRoute = { params: { poiId: "poi-1", poiName: "Taj Mahal" } };
jest.mock("@react-navigation/native", () => ({
  ...jest.requireActual("@react-navigation/native"),
  useNavigation: () => mockNavigation,
  useRoute: () => mockRoute,
}));

jest.mock("../../i18n", () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { en } = require("../../i18n/locales/en");
  const t = (key: string): unknown =>
    key.split(".").reduce((acc: unknown, part: string) => (acc as never)?.[part], en) ?? key;
  return { useTranslation: () => ({ t }) };
});

jest.mock("../../api/heritage", () => ({
  fetchNarration: jest.fn(),
}));

const mockFetchNarration = fetchNarration as jest.Mock;

describe("HeritageNarrationScreen", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders the grounded narration and its sources", async () => {
    mockFetchNarration.mockResolvedValue({
      poi_id: "poi-1",
      poi_name: "Taj Mahal",
      layer: "overview",
      narration: "The Taj Mahal is an ivory-white marble mausoleum.",
      confidence: "high",
      sources: ["Overview"],
    });

    await render(<HeritageNarrationScreen />);

    await waitFor(() => expect(screen.getByTestId("narration-content")).toBeTruthy());
    expect(screen.getByText("The Taj Mahal is an ivory-white marble mausoleum.")).toBeTruthy();
    expect(screen.getByText("Sourced from: Overview")).toBeTruthy();
    expect(screen.queryByTestId("narration-confidence")).toBeNull();
  });

  it("shows the low-confidence disclaimer when confidence is low", async () => {
    mockFetchNarration.mockResolvedValue({
      poi_id: "poi-1",
      poi_name: "Taj Mahal",
      layer: "overview",
      narration: "Some detail about the carvings.",
      confidence: "low",
      sources: ["Overview"],
    });

    await render(<HeritageNarrationScreen />);

    await waitFor(() => expect(screen.getByTestId("narration-confidence")).toBeTruthy());
  });

  it("shows a not-covered state without fabricating anything", async () => {
    mockFetchNarration.mockRejectedValue(
      new ApiError(404, "We don't have verified heritage information yet.", "POI_NOT_COVERED"),
    );

    await render(<HeritageNarrationScreen />);

    await waitFor(() => expect(screen.getByTestId("narration-not-covered")).toBeTruthy());
  });

  it("shows a typed error state with retry on other failures", async () => {
    mockFetchNarration.mockRejectedValue(new ApiError(503, "Backend unavailable"));

    await render(<HeritageNarrationScreen />);

    await waitFor(() => expect(screen.getByTestId("narration-error")).toBeTruthy());
    expect(screen.getByText("Backend unavailable")).toBeTruthy();
  });

  it("navigates to PhotoQA when the photo FAB is pressed", async () => {
    mockFetchNarration.mockResolvedValue({
      poi_id: "poi-1",
      poi_name: "Taj Mahal",
      layer: "overview",
      narration: "text",
      confidence: "high",
      sources: ["Overview"],
    });

    await render(<HeritageNarrationScreen />);
    await waitFor(() => expect(screen.getByTestId("open-photo-qa-fab")).toBeTruthy());

    fireEvent.press(screen.getByTestId("open-photo-qa-fab"));

    expect(mockNavigate).toHaveBeenCalledWith("PhotoQA", { poiId: "poi-1", poiName: "Taj Mahal" });
  });
});
