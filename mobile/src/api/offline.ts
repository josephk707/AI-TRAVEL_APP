/**
 * Typed call to /v1/trips/{id}/offline-package — F26 Offline Heritage
 * Access, see app/services/offline_service.py's module docstring for the
 * documented scope (real heritage/phrasebook/itinerary bundle; map-tile
 * caching explicitly out of scope).
 */

import { apiGet } from "./client";
import type { PhrasebookEntry } from "./phrasebook";

export interface OfflinePoi {
  poi_id: string;
  name: string;
  category: string;
  lat: number;
  lng: number;
}

export interface OfflineHeritageSection {
  poi_id: string;
  section_title: string | null;
  body_text: string;
  source_citation: string | null;
}

export interface OfflinePackage {
  trip_id: string;
  packaged_at: string;
  pois: OfflinePoi[];
  heritage_content: OfflineHeritageSection[];
  phrasebook_entries: PhrasebookEntry[];
}

interface Envelope<T> {
  data: T;
}

export async function fetchOfflinePackage(tripId: string): Promise<OfflinePackage> {
  const envelope = await apiGet<Envelope<OfflinePackage>>(`/v1/trips/${tripId}/offline-package`);
  return envelope.data;
}
