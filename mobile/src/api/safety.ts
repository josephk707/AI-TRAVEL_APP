/**
 * Typed calls to /v1/safety/*, /v1/trips/{id}/share/* — F21 Safety/SOS,
 * see docs/API_SPECIFICATION.md §16.
 */

import { apiGet, apiPost } from "./client";

export interface TrustedContact {
  id: string;
  user_id: string;
  name: string;
  phone: string | null;
  email: string | null;
  created_at: string;
}

export interface ShareStartResult {
  id: string;
  trip_id: string;
  share_token: string;
  is_active: boolean;
  started_at: string;
  expires_at: string;
  share_url: string;
}

export interface SosResult {
  id: string;
  triggered_at: string;
  last_known_lat: number | null;
  last_known_lng: number | null;
  location_captured_at: string | null;
  contacts_notified: number;
}

interface Envelope<T> {
  data: T;
}

export async function addTrustedContact(
  name: string,
  phone?: string,
  email?: string,
): Promise<TrustedContact> {
  const envelope = await apiPost<Envelope<TrustedContact>>("/v1/safety/contacts", {
    name,
    phone,
    email,
  });
  return envelope.data;
}

export async function listTrustedContacts(signal?: AbortSignal): Promise<TrustedContact[]> {
  const envelope = await apiGet<Envelope<TrustedContact[]>>("/v1/safety/contacts", signal);
  return envelope.data;
}

export async function startLocationShare(tripId: string): Promise<ShareStartResult> {
  const envelope = await apiPost<Envelope<ShareStartResult>>(`/v1/trips/${tripId}/share/start`);
  return envelope.data;
}

export async function stopLocationShare(tripId: string): Promise<void> {
  await apiPost(`/v1/trips/${tripId}/share/stop`);
}

export async function triggerSos(tripId?: string): Promise<SosResult> {
  const envelope = await apiPost<Envelope<SosResult>>("/v1/safety/sos", { trip_id: tripId });
  return envelope.data;
}
