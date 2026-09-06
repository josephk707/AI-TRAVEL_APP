/**
 * Typed calls to /v1/auth/* — see docs/API_SPECIFICATION.md §2.
 */

import { apiGet, apiPatch, apiPost } from "./client";
import type { LanguageCode } from "../i18n/languages";

export interface ProfileData {
  id: string;
  display_name: string | null;
  avatar_url: string | null;
  home_region: string | null;
  travel_style: string | null;
  pace: string | null;
  budget_bracket: string | null;
  travel_companion: string | null;
  trip_motivation: string | null;
  role: string;
  preferred_language: LanguageCode;
  onboarding_completed_at: string | null;
  created_at: string;
  updated_at: string;
}

interface Envelope<T> {
  data: T;
}

export async function bootstrapSession(): Promise<{ profile: ProfileData; created: boolean }> {
  const envelope = await apiPost<Envelope<{ profile: ProfileData; created: boolean }>>(
    "/v1/auth/session/bootstrap",
  );
  return envelope.data;
}

export async function fetchMyProfile(signal?: AbortSignal): Promise<ProfileData> {
  const envelope = await apiGet<Envelope<ProfileData>>("/v1/auth/me", signal);
  return envelope.data;
}

export async function logout(): Promise<void> {
  await apiPost<Envelope<{ status: string }>>("/v1/auth/logout");
}

/** Language Settings phase — persists the caller's UI-language preference
 * server-side (PATCH /v1/auth/me), so it survives reinstall/new-device
 * login, not just this device's local storage. See LanguageContext. */
export async function updatePreferredLanguage(
  preferredLanguage: LanguageCode,
  signal?: AbortSignal,
): Promise<ProfileData> {
  const envelope = await apiPatch<Envelope<ProfileData>>(
    "/v1/auth/me",
    { preferred_language: preferredLanguage },
    signal,
  );
  return envelope.data;
}
