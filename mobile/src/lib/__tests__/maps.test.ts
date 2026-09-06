import { Linking } from "react-native";

import { buildMapsUrl, openInMaps } from "../maps";

describe("buildMapsUrl", () => {
  it("prefers verified coordinates", () => {
    expect(buildMapsUrl({ poi_name: "Red Fort", area: null, lat: 28.6562, lng: 77.241 })).toBe(
      "https://www.google.com/maps/search/?api=1&query=28.6562,77.241",
    );
  });

  it("falls back to a name + area search when there are no coordinates", () => {
    expect(
      buildMapsUrl({ poi_name: "Humayun's Tomb", area: "Nizamuddin", lat: null, lng: null }),
    ).toBe("https://www.google.com/maps/search/?api=1&query=Humayun's%20Tomb%2C%20Nizamuddin");
  });

  it("returns null when there is nothing to search for", () => {
    expect(buildMapsUrl({ poi_name: null, area: null, lat: null, lng: null })).toBeNull();
  });
});

describe("openInMaps", () => {
  it("opens the URL and reports success", async () => {
    const spy = jest.spyOn(Linking, "openURL").mockResolvedValue(true);

    await expect(
      openInMaps({ poi_name: "Red Fort", area: null, lat: 28.6562, lng: 77.241 }),
    ).resolves.toBe(true);
    expect(spy).toHaveBeenCalledWith("https://www.google.com/maps/search/?api=1&query=28.6562,77.241");
    spy.mockRestore();
  });

  it("reports failure instead of throwing when the link cannot open", async () => {
    const spy = jest.spyOn(Linking, "openURL").mockRejectedValue(new Error("no handler"));

    await expect(
      openInMaps({ poi_name: "Red Fort", area: null, lat: 28.6562, lng: 77.241 }),
    ).resolves.toBe(false);
    spy.mockRestore();
  });

  it("does nothing for a stop with no name and no coordinates", async () => {
    const spy = jest.spyOn(Linking, "openURL").mockResolvedValue(true);

    await expect(openInMaps({ poi_name: null, area: null, lat: null, lng: null })).resolves.toBe(false);
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
