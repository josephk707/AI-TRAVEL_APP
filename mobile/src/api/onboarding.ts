/**
 * Typed calls to /v1/onboarding/* — see docs/API_SPECIFICATION.md §3.
 */

import { apiGet, apiPost } from "./client";
import type { BudgetBracket, Pace, TravelStyle } from "../onboarding/onboardingOptions";

export interface InterestOption {
  id: number;
  slug: string;
  label: string;
}

export interface OnboardingResponseData {
  onboarding_completed: boolean;
  onboarding_completed_at: string | null;
  interest_ids: number[];
  travel_style: TravelStyle | null;
  pace: Pace | null;
  budget_bracket: BudgetBracket | null;
}

export interface OnboardingStatus {
  onboarding_completed: boolean;
  onboarding_completed_at: string | null;
}

interface Envelope<T> {
  data: T;
  meta?: { saved?: boolean | null } | null;
}

export async function fetchInterests(signal?: AbortSignal): Promise<InterestOption[]> {
  const envelope = await apiGet<Envelope<InterestOption[]>>("/v1/onboarding/interests", signal);
  return envelope.data;
}

export async function fetchOnboardingStatus(signal?: AbortSignal): Promise<OnboardingStatus> {
  const envelope = await apiGet<Envelope<OnboardingStatus>>("/v1/onboarding/status", signal);
  return envelope.data;
}

export interface SubmitOnboardingResponsesInput {
  interest_ids: number[];
  travel_style?: TravelStyle | null;
  pace?: Pace | null;
  budget_bracket?: BudgetBracket | null;
}

export interface SubmitOnboardingResponsesResult {
  data: OnboardingResponseData;
  saved: boolean;
}

export async function submitOnboardingResponses(
  payload: SubmitOnboardingResponsesInput,
): Promise<SubmitOnboardingResponsesResult> {
  const envelope = await apiPost<Envelope<OnboardingResponseData>>(
    "/v1/onboarding/responses",
    payload,
  );
  // saved defaults true: the request only reaches here on a 2xx response
  // (apiPost/request() throws ApiError on non-2xx), and the backend only
  // ever omits meta.saved on paths that don't set it — this endpoint always
  // does, but the fallback keeps this resilient to a genuinely absent flag
  // rather than reading `undefined` as falsy-but-wrong.
  return { data: envelope.data, saved: envelope.meta?.saved ?? true };
}
