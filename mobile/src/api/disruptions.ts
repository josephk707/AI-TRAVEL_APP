/**
 * Typed calls to /v1/trips/{id}/disruptions* — F20 Dynamic Itinerary
 * Re-Adaptation Engine, see app/schemas/disruption.py's module docstring
 * (resolving ARCHITECTURE_REVIEW.md H2) for the endpoint contract.
 */

import { apiGet, apiPost } from "./client";

export type DisruptionTriggerType =
  | "weather"
  | "closure"
  | "delay"
  | "off_route"
  | "missed_activity"
  | "budget_overrun"
  | "schedule_change"
  | "manual_request";

export interface DisruptionAlternative {
  poi_id: string;
  poi_name: string;
  lat: number;
  lng: number;
}

export interface DisruptionProposal {
  reason: string;
  alternatives: DisruptionAlternative[];
}

export interface DisruptionEvent {
  id: string;
  trip_id: string;
  itinerary_item_id: string;
  trigger_type: DisruptionTriggerType;
  detected_at: string;
  proposal: DisruptionProposal;
  status: "proposed" | "accepted" | "dismissed";
  resolved_at: string | null;
}

interface Envelope<T> {
  data: T;
}

export async function listDisruptions(tripId: string, signal?: AbortSignal): Promise<DisruptionEvent[]> {
  const envelope = await apiGet<Envelope<DisruptionEvent[]>>(
    `/v1/trips/${tripId}/disruptions`,
    signal,
  );
  return envelope.data;
}

export async function checkForDisruptions(tripId: string): Promise<DisruptionEvent[]> {
  const envelope = await apiPost<Envelope<DisruptionEvent[]>>(
    `/v1/trips/${tripId}/disruptions/check`,
  );
  return envelope.data;
}

export async function resolveDisruption(
  tripId: string,
  eventId: string,
  decision: "accept" | "dismiss",
  alternativeIndex?: number,
): Promise<DisruptionEvent> {
  const envelope = await apiPost<Envelope<DisruptionEvent>>(
    `/v1/trips/${tripId}/disruptions/${eventId}/resolve`,
    { decision, alternative_index: alternativeIndex },
  );
  return envelope.data;
}
