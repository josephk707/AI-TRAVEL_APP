/**
 * Typed calls to /v1/trips/* — F3/F4/F5/F12, see docs/API_SPECIFICATION.md §4.
 */

import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export type TripStatus = "draft" | "upcoming" | "active" | "completed" | "cancelled";
export type GenerationStatus = "none" | "pending" | "succeeded" | "fallback_used" | "failed";
export type ItemStatus = "planned" | "confirmed" | "skipped" | "completed";

export interface Trip {
  id: string;
  owner_id: string;
  title: string;
  destination: string;
  destination_lat: number | null;
  destination_lng: number | null;
  start_date: string | null;
  end_date: string | null;
  status: TripStatus;
  trip_type: "solo" | "group" | "quick_plan";
  budget_planned: number | null;
  budget_currency: string;
  generation_status: GenerationStatus;
  created_at: string;
  updated_at: string;
}

export interface ItineraryItem {
  id: string;
  poi_id: string | null;
  poi_name: string | null;
  sequence_order: number;
  planned_start: string | null;
  planned_end: string | null;
  estimated_duration_min: number | null;
  estimated_cost: number | null;
  status: ItemStatus;
  source: "ai" | "user" | "imported";
  verify_on_arrival: boolean;
  weather_flag: boolean;
  weather_alternative_suggestion: string | null;
  notes: string | null;
}

export interface ItineraryDay {
  day_number: number;
  date: string | null;
  items: ItineraryItem[];
}

export interface BudgetSummary {
  estimated_total: number;
  planned_budget: number | null;
  over_budget: boolean;
  tolerance_pct: number;
}

export interface TripNote {
  id: string;
  trip_id: string;
  raw_text: string;
  extracted_places: Record<string, unknown>[] | null;
  unparsed_remainder: string | null;
  conflicts: string[];
  parsed_at: string | null;
  created_at: string;
}

interface Envelope<T> {
  data: T;
  meta?: { degraded_mode?: boolean | null; message?: string | null } | null;
}

export interface CreateTripInput {
  title: string;
  destination: string;
  destination_lat?: number;
  destination_lng?: number;
  start_date?: string;
  end_date?: string;
  budget_planned?: number;
  budget_currency?: string;
}

export async function createTrip(input: CreateTripInput): Promise<Trip> {
  const envelope = await apiPost<Envelope<Trip>>("/v1/trips", input);
  return envelope.data;
}

export async function listTrips(signal?: AbortSignal): Promise<Trip[]> {
  const envelope = await apiGet<Envelope<Trip[]>>("/v1/trips", signal);
  return envelope.data;
}

export async function fetchTrip(tripId: string, signal?: AbortSignal): Promise<Trip> {
  const envelope = await apiGet<Envelope<Trip>>(`/v1/trips/${tripId}`, signal);
  return envelope.data;
}

export async function updateTrip(tripId: string, input: Partial<CreateTripInput & { status: TripStatus }>): Promise<Trip> {
  const envelope = await apiPatch<Envelope<Trip>>(`/v1/trips/${tripId}`, input);
  return envelope.data;
}

export async function deleteTrip(tripId: string): Promise<void> {
  await apiDelete(`/v1/trips/${tripId}`);
}

export async function submitTripNotes(tripId: string, rawText: string): Promise<TripNote> {
  const envelope = await apiPost<Envelope<TripNote>>(`/v1/trips/${tripId}/notes`, {
    raw_text: rawText,
  });
  return envelope.data;
}

export interface GenerateItineraryInput {
  interests?: string[];
  budget?: number;
  time_window?: { start: string; end: string };
  destination?: string;
  use_own_ideas?: boolean;
}

export interface GenerateItineraryResult {
  trip_id: string;
  generation_status: GenerationStatus;
  summary: string;
  days: ItineraryDay[];
  budget_summary: BudgetSummary | null;
  conflicts: string[];
  degraded: boolean;
  degradedMessage: string | null;
}

export async function generateItinerary(
  tripId: string,
  input: GenerateItineraryInput,
): Promise<GenerateItineraryResult> {
  const envelope = await apiPost<
    Envelope<{
      trip_id: string;
      generation_status: GenerationStatus;
      summary: string;
      days: ItineraryDay[];
      budget_summary: BudgetSummary | null;
      conflicts: string[];
    }>
  >(`/v1/trips/${tripId}/itinerary/generate`, input);
  return {
    ...envelope.data,
    degraded: envelope.meta?.degraded_mode ?? false,
    degradedMessage: envelope.meta?.message ?? null,
  };
}

export interface ModifyItineraryResult {
  reply: string;
  changed_item_ids: string[];
  days: ItineraryDay[];
}

export async function modifyItinerary(tripId: string, message: string): Promise<ModifyItineraryResult> {
  const envelope = await apiPost<Envelope<ModifyItineraryResult>>(
    `/v1/trips/${tripId}/itinerary/modify`,
    { message },
  );
  return envelope.data;
}

export async function fetchItinerary(tripId: string, signal?: AbortSignal): Promise<ItineraryDay[]> {
  const envelope = await apiGet<Envelope<ItineraryDay[]>>(`/v1/trips/${tripId}/itinerary`, signal);
  return envelope.data;
}

export async function updateItineraryItem(
  tripId: string,
  itemId: string,
  input: Partial<Pick<ItineraryItem, "planned_start" | "planned_end" | "status" | "notes">>,
): Promise<ItineraryItem> {
  const envelope = await apiPatch<Envelope<ItineraryItem>>(
    `/v1/trips/${tripId}/itinerary/items/${itemId}`,
    input,
  );
  return envelope.data;
}
