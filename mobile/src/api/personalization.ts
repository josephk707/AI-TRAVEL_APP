/**
 * Typed call to GET /v1/personalization/travel-dna — Final Personalization
 * phase. See backend/app/schemas/personalization.py for the response
 * shape this mirrors exactly.
 */

import { apiGet } from "./client";

export interface TravelDna {
  travel_style: string | null;
  pace: string | null;
  budget_bracket: string | null;
  travel_companion: string | null;
  trip_motivation: string | null;
  interests: string[];
  favorite_categories: Record<string, number>;
  trips_planned: number;
  places_saved: number;
  travel_personality: string;
  summary: string;
  generated_by: "ai" | "template";
  updated_at: string;
}

interface Envelope<T> {
  data: T;
}

export async function fetchTravelDna(signal?: AbortSignal): Promise<TravelDna> {
  const envelope = await apiGet<Envelope<TravelDna>>("/v1/personalization/travel-dna", signal);
  return envelope.data;
}
