import { Linking } from "react-native";

import type { ItineraryItem } from "../api/trips";

/**
 * Deep link into Google Maps for turn-by-turn navigation to an itinerary
 * stop (AI-first itinerary phase — every stop is tappable). The Maps URL
 * scheme opens the native app where installed (iOS/Android) and the web
 * app otherwise, so one URL serves every platform this client runs on.
 * Verified coordinates are preferred; a stop with none is searched by
 * name and area instead, so it still opens somewhere useful.
 */
export function buildMapsUrl(item: Pick<ItineraryItem, "poi_name" | "area" | "lat" | "lng">): string | null {
  if (item.lat != null && item.lng != null) {
    return `https://www.google.com/maps/search/?api=1&query=${item.lat},${item.lng}`;
  }
  const label = [item.poi_name, item.area].filter(Boolean).join(", ");
  if (!label) return null;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(label)}`;
}

export async function openInMaps(
  item: Pick<ItineraryItem, "poi_name" | "area" | "lat" | "lng">,
): Promise<boolean> {
  const url = buildMapsUrl(item);
  if (!url) return false;
  try {
    await Linking.openURL(url);
    return true;
  } catch {
    return false;
  }
}
