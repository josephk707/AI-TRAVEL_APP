/**
 * Typed calls to /v1/trips/{id}/invite, /v1/trips/invite/{token}/accept,
 * /v1/trips/{id}/members/*, /v1/trips/{id}/itinerary/reconcile — F19
 * Group/Collaborative Trip Planning, see docs/API_SPECIFICATION.md §13.
 */

import { apiGet, apiPost } from "./client";
import type { ItineraryDay } from "./trips";

export interface Invite {
  id: string;
  trip_id: string;
  method: "link" | "email";
  email: string | null;
  token: string;
  status: "pending" | "accepted" | "expired";
  expires_at: string;
  invite_url: string;
}

export interface InviteAcceptResult {
  trip_id: string;
  role: "organiser" | "member";
  joined: boolean;
}

export interface TripMember {
  trip_id: string;
  user_id: string;
  display_name: string | null;
  role: "organiser" | "member";
  invite_status: "invited" | "accepted" | "declined" | "no_response";
  invited_at: string;
  responded_at: string | null;
}

export interface MemberPreferences {
  trip_id: string;
  user_id: string;
  interests: string[];
  budget_max: number | null;
  constraints: Record<string, unknown>;
  submitted_at: string;
}

export interface ReconcileConflict {
  field: string;
  description: string;
  resolution: string;
}

export interface ReconcileResult {
  trip_id: string;
  generation_status: string;
  summary: string;
  days: ItineraryDay[];
  conflicts: ReconcileConflict[];
  included_member_ids: string[];
  excluded_member_ids: string[];
}

interface Envelope<T> {
  data: T;
}

export async function createInvite(
  tripId: string,
  method: "link" | "email",
  email?: string,
): Promise<Invite> {
  const envelope = await apiPost<Envelope<Invite>>(`/v1/trips/${tripId}/invite`, {
    method,
    email,
  });
  return envelope.data;
}

export async function acceptInvite(inviteToken: string): Promise<InviteAcceptResult> {
  const envelope = await apiPost<Envelope<InviteAcceptResult>>(
    `/v1/trips/invite/${inviteToken}/accept`,
  );
  return envelope.data;
}

export async function submitMemberPreferences(
  tripId: string,
  userId: string,
  interests: string[],
  budgetMax?: number,
  constraints?: Record<string, unknown>,
): Promise<MemberPreferences> {
  const envelope = await apiPost<Envelope<MemberPreferences>>(
    `/v1/trips/${tripId}/members/${userId}/preferences`,
    { interests, budget_max: budgetMax, constraints: constraints ?? {} },
  );
  return envelope.data;
}

export async function listTripMembers(tripId: string, signal?: AbortSignal): Promise<TripMember[]> {
  const envelope = await apiGet<Envelope<TripMember[]>>(`/v1/trips/${tripId}/members`, signal);
  return envelope.data;
}

export async function reconcileItinerary(tripId: string): Promise<ReconcileResult> {
  const envelope = await apiPost<Envelope<ReconcileResult>>(
    `/v1/trips/${tripId}/itinerary/reconcile`,
  );
  return envelope.data;
}
