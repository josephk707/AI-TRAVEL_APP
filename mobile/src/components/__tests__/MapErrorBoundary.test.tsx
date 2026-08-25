import { render, screen } from "@testing-library/react-native";
import React from "react";
import { Text } from "react-native";

import { MapErrorBoundary } from "../MapErrorBoundary";

function Bomb(): React.JSX.Element {
  throw new Error("simulated map render failure");
}

describe("MapErrorBoundary", () => {
  it("renders children normally when nothing throws", async () => {
    await render(
      <MapErrorBoundary fallback={<Text testID="fallback">fallback</Text>}>
        <Text testID="map">map</Text>
      </MapErrorBoundary>,
    );

    expect(screen.getByTestId("map")).toBeTruthy();
    expect(screen.queryByTestId("fallback")).toBeNull();
  });

  it("swaps to the fallback (list view) when the map throws during render", async () => {
    const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});

    await render(
      <MapErrorBoundary fallback={<Text testID="fallback">fallback</Text>}>
        <Bomb />
      </MapErrorBoundary>,
    );

    expect(screen.getByTestId("fallback")).toBeTruthy();
    expect(screen.queryByTestId("map")).toBeNull();
    consoleErrorSpy.mockRestore();
  });
});
