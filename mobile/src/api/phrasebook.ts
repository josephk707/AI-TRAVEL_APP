/**
 * Typed calls to /v1/phrasebook/{region}, /v1/trips/{id}/phrasebook/download
 * — F10 static Local Phrase Assistant, see docs/API_SPECIFICATION.md §9.
 */

import { apiGet, apiPost } from "./client";

export interface PhrasebookEntry {
  id: string;
  region: string;
  language_code: string;
  category: string;
  phrase_en: string;
  phrase_local_script: string;
  phrase_transliteration: string;
  audio_url: string | null;
  created_at: string;
}

interface Envelope<T> {
  data: T;
}

export async function fetchPhrasebook(
  region: string,
  options?: { language?: string; category?: string },
  signal?: AbortSignal,
): Promise<PhrasebookEntry[]> {
  const params = new URLSearchParams();
  if (options?.language) params.set("language", options.language);
  if (options?.category) params.set("category", options.category);
  const query = params.toString();
  const envelope = await apiGet<Envelope<PhrasebookEntry[]>>(
    `/v1/phrasebook/${encodeURIComponent(region)}${query ? `?${query}` : ""}`,
    signal,
  );
  return envelope.data;
}

export async function downloadTripPhrasebook(tripId: string): Promise<PhrasebookEntry[]> {
  const envelope = await apiPost<Envelope<PhrasebookEntry[]>>(
    `/v1/trips/${tripId}/phrasebook/download`,
  );
  return envelope.data;
}
