/**
 * Typed calls to /v1/trips/{id}/memory-items — F11 Trip Memory Box, see
 * docs/API_SPECIFICATION.md §10. Binary upload itself goes directly from
 * this client to Supabase Storage (RLS-mediated) — this file only ever
 * talks to the backend's metadata endpoints, per
 * app/services/memory_service.py's own documented contract.
 */

import { apiDelete, apiGet, apiPost } from "./client";

export type MemoryItemType = "photo" | "video" | "note";

export interface MemoryItem {
  id: string;
  trip_id: string;
  user_id: string;
  item_type: MemoryItemType;
  storage_path: string | null;
  caption: string | null;
  taken_at: string | null;
  uploaded_at: string;
  retention_expires_at: string;
  expiry_reminder_sent_at: string | null;
  downloaded_at: string | null;
}

interface Envelope<T> {
  data: T;
}

export interface CreateMemoryItemInput {
  item_type: MemoryItemType;
  storage_path?: string;
  caption?: string;
  taken_at?: string;
}

export async function createMemoryItem(
  tripId: string,
  input: CreateMemoryItemInput,
): Promise<MemoryItem> {
  const envelope = await apiPost<Envelope<MemoryItem>>(
    `/v1/trips/${tripId}/memory-items`,
    input,
  );
  return envelope.data;
}

export async function listMemoryItems(tripId: string, signal?: AbortSignal): Promise<MemoryItem[]> {
  const envelope = await apiGet<Envelope<MemoryItem[]>>(`/v1/trips/${tripId}/memory-items`, signal);
  return envelope.data;
}

export async function deleteMemoryItem(tripId: string, itemId: string): Promise<void> {
  await apiDelete(`/v1/trips/${tripId}/memory-items/${itemId}`);
}
