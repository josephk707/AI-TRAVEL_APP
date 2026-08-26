/**
 * Typed calls to /v1/heritage/* — F8 Heritage Narration RAG + F9 Visual
 * Q&A, see docs/API_SPECIFICATION.md §7/§8.
 */

import { apiGet, apiPostFormData } from "./client";

export type HeritageLayer = "overview" | "deep";
export type Confidence = "high" | "low";

export interface NarrationResult {
  poi_id: string;
  poi_name: string;
  layer: HeritageLayer;
  narration: string;
  confidence: Confidence;
  sources: string[];
}

export interface PhotoQaResult {
  poi_id: string | null;
  answer: string;
  confidence: Confidence;
  grounded: boolean;
}

interface Envelope<T> {
  data: T;
}

export async function fetchNarration(
  poiId: string,
  layer: HeritageLayer = "overview",
  section?: string,
): Promise<NarrationResult> {
  const query = new URLSearchParams({ layer });
  if (section) query.set("section", section);
  const envelope = await apiGet<Envelope<NarrationResult>>(
    `/v1/heritage/${poiId}/narration?${query.toString()}`,
  );
  return envelope.data;
}

export async function askPhotoQuestion(
  poiId: string,
  question: string,
  photoUri: string,
): Promise<PhotoQaResult> {
  const formData = new FormData();
  formData.append("question", question);
  // React Native's fetch FormData accepts this { uri, name, type } shape
  // directly — no Blob conversion needed, matching Expo's own documented
  // upload pattern for images picked via expo-image-picker.
  formData.append("image", {
    uri: photoUri,
    name: "photo.jpg",
    type: "image/jpeg",
  } as unknown as Blob);

  const envelope = await apiPostFormData<Envelope<PhotoQaResult>>(
    `/v1/heritage/${poiId}/photo-qa`,
    formData,
  );
  return envelope.data;
}
