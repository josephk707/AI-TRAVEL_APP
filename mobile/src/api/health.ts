/**
 * Typed call to the backend's real /healthz endpoint.
 *
 * This exists specifically to prove the mobile <-> backend API client
 * foundation actually works end-to-end (CLAUDE.md §2's USER INTERFACE ->
 * API -> ... -> RESPONSE -> USER INTERFACE bar) rather than being an
 * unverified assumption — the FoundationScreen calls this on mount.
 */

import { apiGet } from "./client";

export interface LivenessData {
  status: string;
  app_name: string;
  app_version: string;
  environment: string;
}

interface Envelope<T> {
  data: T;
}

export async function fetchBackendHealth(signal?: AbortSignal): Promise<LivenessData> {
  const envelope = await apiGet<Envelope<LivenessData>>("/healthz", signal);
  return envelope.data;
}
