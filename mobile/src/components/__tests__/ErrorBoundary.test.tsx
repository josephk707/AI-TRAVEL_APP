import React from "react";
import { Text } from "react-native";
import { fireEvent, render, screen } from "@testing-library/react-native";

import { ErrorBoundary } from "../ErrorBoundary";

function Bomb(): React.JSX.Element {
  throw new Error("boom");
}

describe("ErrorBoundary", () => {
  let consoleErrorSpy: jest.SpyInstance;

  beforeEach(() => {
    // React logs the caught error to console.error by default; silence it
    // for this expected-failure test without hiding unexpected failures
    // elsewhere.
    consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it("renders children normally when nothing throws", async () => {
    await render(
      <ErrorBoundary>
        <Text>all good</Text>
      </ErrorBoundary>,
    );
    expect(screen.getByText("all good")).toBeTruthy();
  });

  it("catches a render error and shows the fallback instead of crashing", async () => {
    await render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId("error-boundary-fallback")).toBeTruthy();
    expect(screen.getByText("boom")).toBeTruthy();
  });

  it("lets the user reset the boundary via the retry button", async () => {
    await render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>,
    );
    fireEvent.press(screen.getByText("Try again"));
    // After reset, ErrorBoundary re-renders children, which throw again
    // immediately (Bomb always throws) — so the fallback should still be
    // showing rather than the app being left in a broken, un-rendered state.
    expect(screen.getByTestId("error-boundary-fallback")).toBeTruthy();
  });
});
