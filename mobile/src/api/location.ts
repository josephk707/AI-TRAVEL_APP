/**
 * Typed calls to /v1/trips/{id}/location/*, /nearby — F7 Real-Time
 * Location Companion, see docs/API_SPECIFICATION.md §6.
 */

import { apiGet, apiPost } from "./client";

export interface ArrivalEvent {
  itinerary_item_id: string;
  poi_name: string;
}

export interface NearbyPoi {
  poi_id: string;
  name: string;
  distance_m: number;
}

export interface LocationPingResult {
  arrival_event: ArrivalEvent | null;
  nearby: NearbyPoi[];
}

interface Envelope<T> {
  data: T;
}

export async function setLocationConsent(tripId: string, consent: boolean): Promise<void> {
  await apiPost<Envelope<{ consent: boolean }>>(`/v1/trips/${tripId}/location/consent`, {
    consent,
  });
}

export async function submitLocationPing(
  tripId: string,
  lat: number,
  lng: number,
): Promise<LocationPingResult> {
  const envelope = await apiPost<Envelope<LocationPingResult>>(
    `/v1/trips/${tripId}/location/ping`,
    { lat, lng },
  );
  return envelope.data;
}

export async function submitManualLocation(tripId: string, poiId: string): Promise<LocationPingResult> {
  const envelope = await apiPost<Envelope<LocationPingResult>>(
    `/v1/trips/${tripId}/location/manual`,
    { poi_id: poiId },
  );
  return envelope.data;
}

export async function fetchNearby(
  tripId: string,
  lat: number,
  lng: number,
  signal?: AbortSignal,
): Promise<NearbyPoi[]> {
  const envelope = await apiGet<Envelope<NearbyPoi[]>>(
    `/v1/trips/${tripId}/nearby?lat=${lat}&lng=${lng}`,
    signal,
  );
  return envelope.data;
}
