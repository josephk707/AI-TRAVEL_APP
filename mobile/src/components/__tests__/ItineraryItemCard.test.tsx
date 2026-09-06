import { act, fireEvent, render, screen } from "@testing-library/react-native";
import React from "react";
import { Linking } from "react-native";

import type { ItineraryItem } from "../../api/trips";
import { ItineraryItemCard } from "../ItineraryItemCard";

function makeItem(overrides: Partial<ItineraryItem> = {}): ItineraryItem {
  return {
    id: "item-1",
    poi_id: "poi-1",
    poi_name: "Humayun's Tomb",
    poi_category: "heritage",
    area: "Nizamuddin",
    lat: 28.5933,
    lng: 77.2506,
    location_source: "places_api",
    sequence_order: 0,
    planned_start: "14:00",
    planned_end: "15:30",
    estimated_duration_min: 90,
    estimated_cost: 35,
    status: "planned",
    source: "ai",
    verify_on_arrival: false,
    weather_flag: false,
    weather_alternative_suggestion: null,
    notes: "Fits your heritage interest.",
    ...overrides,
  };
}

describe("ItineraryItemCard", () => {
  it("renders the stop with its area, reason and a navigate action", async () => {
    await render(<ItineraryItemCard item={makeItem()} testID="item-1" />);

    expect(screen.getByText("Humayun's Tomb")).toBeTruthy();
    expect(screen.getByText("Nizamuddin")).toBeTruthy();
    expect(screen.getByText("Fits your heritage interest.")).toBeTruthy();
    expect(screen.getByTestId("item-1-navigate")).toBeTruthy();
    expect(screen.queryByTestId("item-1-approx")).toBeNull();
    expect(screen.queryByTestId("item-1-unverified")).toBeNull();
  });

  it("opens Google Maps at the stop's coordinates when Navigate is pressed", async () => {
    const spy = jest.spyOn(Linking, "openURL").mockResolvedValue(true);
    await render(<ItineraryItemCard item={makeItem()} testID="item-1" />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("item-1-navigate"));
    });

    expect(spy).toHaveBeenCalledWith(
      "https://www.google.com/maps/search/?api=1&query=28.5933,77.2506",
    );
    spy.mockRestore();
  });

  it("labels an approximate location honestly and still navigates", async () => {
    await render(
      <ItineraryItemCard item={makeItem({ location_source: "ai_estimate" })} testID="item-1" />,
    );

    expect(screen.getByTestId("item-1-approx")).toBeTruthy();
    expect(screen.getByTestId("item-1-navigate")).toBeTruthy();
  });

  it("labels an unverified location and navigates by name", async () => {
    const spy = jest.spyOn(Linking, "openURL").mockResolvedValue(true);
    await render(
      <ItineraryItemCard
        item={makeItem({ location_source: "unresolved", lat: null, lng: null, poi_id: null })}
        testID="item-1"
      />,
    );

    expect(screen.getByTestId("item-1-unverified")).toBeTruthy();
    await act(async () => {
      fireEvent.press(screen.getByTestId("item-1-navigate"));
    });
    expect(spy).toHaveBeenCalledWith(
      "https://www.google.com/maps/search/?api=1&query=Humayun's%20Tomb%2C%20Nizamuddin",
    );
    spy.mockRestore();
  });

  it("shows a message instead of throwing when Maps cannot be opened", async () => {
    const spy = jest.spyOn(Linking, "openURL").mockRejectedValue(new Error("no handler"));
    await render(<ItineraryItemCard item={makeItem()} testID="item-1" />);

    await act(async () => {
      fireEvent.press(screen.getByTestId("item-1-navigate"));
    });

    expect(screen.getByText("Couldn't open Maps on this device.")).toBeTruthy();
    spy.mockRestore();
  });

  it("shows Free for a zero-cost stop and hides navigation for a skipped one", async () => {
    await render(
      <ItineraryItemCard item={makeItem({ estimated_cost: 0, status: "skipped" })} testID="item-1" />,
    );

    expect(screen.getByText("Free")).toBeTruthy();
    expect(screen.getByText("Skipped")).toBeTruthy();
    expect(screen.queryByTestId("item-1-navigate")).toBeNull();
  });
});
