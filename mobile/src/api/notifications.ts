/**
 * Typed calls to /v1/notifications, /v1/devices/push-token — F16, see
 * docs/API_SPECIFICATION.md §15.
 */

import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export type NotificationType =
  | "arrival"
  | "disruption"
  | "memory_expiry"
  | "sos"
  | "group_invite"
  | "reminder"
  | "system";

export interface AppNotification {
  id: string;
  user_id: string;
  trip_id: string | null;
  type: NotificationType;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  read_at: string | null;
  delivered_channels: string[];
  created_at: string;
}

interface Envelope<T> {
  data: T;
}

export async function listNotifications(
  limit = 30,
  offset = 0,
  signal?: AbortSignal,
): Promise<AppNotification[]> {
  const envelope = await apiGet<Envelope<AppNotification[]>>(
    `/v1/notifications?limit=${limit}&offset=${offset}`,
    signal,
  );
  return envelope.data;
}

export async function markNotificationRead(notificationId: string): Promise<AppNotification> {
  const envelope = await apiPatch<Envelope<AppNotification>>(
    `/v1/notifications/${notificationId}/read`,
  );
  return envelope.data;
}

export async function registerPushToken(
  expoPushToken: string,
  platform: "ios" | "android",
): Promise<void> {
  await apiPost<Envelope<{ registered: boolean }>>("/v1/devices/push-token", {
    expo_push_token: expoPushToken,
    platform,
  });
}

export async function unregisterPushToken(expoPushToken: string): Promise<void> {
  await apiDelete(`/v1/devices/push-token?expo_push_token=${encodeURIComponent(expoPushToken)}`);
}
