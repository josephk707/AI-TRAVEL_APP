/**
 * F16 — Expo push token registration (MOBILE_ARCHITECTURE.md §7,
 * API_SPECIFICATION.md §15). Registers the device's real Expo push token
 * with the backend once signed in; the in-app Notifications Centre
 * remains the guaranteed fallback channel regardless of whether this
 * succeeds (a denied permission, a simulator with no push capability, or
 * a registration failure must never block sign-in or any other flow).
 */

import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

import { registerPushToken, unregisterPushToken } from "../api/notifications";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

let registeredToken: string | null = null;

export async function registerForPushNotifications(): Promise<void> {
  try {
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;
    if (existingStatus !== "granted") {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }
    if (finalStatus !== "granted") return;

    const projectId = Constants.expoConfig?.extra?.eas?.projectId;
    const tokenResponse = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined,
    );
    const token = tokenResponse.data;
    const platform = Platform.OS === "ios" ? "ios" : "android";

    await registerPushToken(token, platform);
    registeredToken = token;
  } catch {
    // No push capability in this environment (simulator, denied
    // permission, missing project config) — the in-app Notifications
    // Centre already covers every notification, so this is a silent,
    // recoverable degrade, not a failure to surface to the user.
  }
}

export async function unregisterCurrentPushToken(): Promise<void> {
  if (!registeredToken) return;
  try {
    await unregisterPushToken(registeredToken);
  } catch {
    // Best-effort cleanup on sign-out — a stale token left registered
    // server-side is harmless (a push to a signed-out device just fails
    // silently on Expo's end) and never worth blocking sign-out over.
  } finally {
    registeredToken = null;
  }
}
