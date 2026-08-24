import React from "react";
import { act, render, screen, waitFor, fireEvent } from "@testing-library/react-native";

import { FoundationScreen } from "../FoundationScreen";
import { ApiError } from "../../api/client";
import { fetchBackendHealth, LivenessData } from "../../api/health";

jest.mock("../../api/health");

const mockedFetchBackendHealth = fetchBackendHealth as jest.MockedFunction<
  typeof fetchBackendHealth
>;

const SAMPLE_HEALTH: LivenessData = {
  status: "ok",
  app_name: "TC-SO1 Backend",
  app_version: "0.1.0",
  environment: "development",
};

describe("FoundationScreen", () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  it("shows a loading state, then the success state on a real successful check", async () => {
    // Deliberately not auto-resolved, so the loading state is deterministically
    // observable before we resolve it ourselves — avoids depending on exactly
    // how many microtask turns `await render()` flushes.
    let resolveHealth!: (value: LivenessData) => void;
    mockedFetchBackendHealth.mockReturnValue(
      new Promise<LivenessData>((resolve) => {
        resolveHealth = resolve;
      }),
    );

    await render(<FoundationScreen />);

    expect(screen.getByTestId("loading-view")).toBeTruthy();

    await act(async () => {
      resolveHealth(SAMPLE_HEALTH);
    });

    await waitFor(() => expect(screen.getByTestId("connectivity-success")).toBeTruthy());
    expect(screen.getByText("TC-SO1 Backend")).toBeTruthy();
  });

  it("shows an error state with a working retry when the backend check fails", async () => {
    mockedFetchBackendHealth.mockRejectedValue(
      new ApiError(0, "Network request failed. Is the backend reachable?", "NETWORK_ERROR"),
    );

    await render(<FoundationScreen />);

    await waitFor(() => expect(screen.getByTestId("connectivity-error")).toBeTruthy());
    expect(screen.getByText("Network request failed. Is the backend reachable?")).toBeTruthy();

    mockedFetchBackendHealth.mockResolvedValue(SAMPLE_HEALTH);
    await act(async () => {
      fireEvent.press(screen.getByTestId("retry-button"));
    });

    await waitFor(() => expect(screen.getByTestId("connectivity-success")).toBeTruthy());
  });
});
