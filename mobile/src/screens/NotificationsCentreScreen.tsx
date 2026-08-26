import { Ionicons } from "@expo/vector-icons";
import { StatusBar } from "expo-status-bar";
import React, { useCallback, useEffect, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { ApiError } from "../api/client";
import { AppNotification, listNotifications, markNotificationRead } from "../api/notifications";
import { Button } from "../components/Button";
import { LoadingView } from "../components/LoadingView";
import { colors, radius, spacing, typography } from "../theme/tokens";

type LoadState =
  | { status: "loading" }
  | { status: "success"; notifications: AppNotification[] }
  | { status: "error"; message: string };

const ICONS: Record<AppNotification["type"], React.ComponentProps<typeof Ionicons>["name"]> = {
  arrival: "location-outline",
  disruption: "warning-outline",
  memory_expiry: "images-outline",
  sos: "alert-circle-outline",
  group_invite: "people-outline",
  reminder: "notifications-outline",
  system: "information-circle-outline",
};

/** F16 — Notifications Centre. The in-app list is the guaranteed fallback
 * channel regardless of push-delivery success (API_SPECIFICATION.md §15
 * / §24) — this screen is real user-scoped data, never a demo feed. */
export function NotificationsCentreScreen(): React.JSX.Element {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const resolveNotifications = useCallback(async (): Promise<LoadState> => {
    try {
      const notifications = await listNotifications();
      return { status: "success", notifications };
    } catch (error) {
      return {
        status: "error",
        message: error instanceof ApiError ? error.message : "Couldn't load your notifications.",
      };
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    resolveNotifications().then((result) => {
      if (!cancelled) setState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [resolveNotifications]);

  const load = useCallback(() => {
    setState({ status: "loading" });
    void resolveNotifications().then(setState);
  }, [resolveNotifications]);

  const markRead = useCallback(
    async (notification: AppNotification) => {
      if (notification.read_at) return;
      try {
        await markNotificationRead(notification.id);
        setState((prev) =>
          prev.status === "success"
            ? {
                status: "success",
                notifications: prev.notifications.map((n) =>
                  n.id === notification.id ? { ...n, read_at: new Date().toISOString() } : n,
                ),
              }
            : prev,
        );
      } catch {
        // Marking read is a convenience, not a critical action — a
        // transient failure here is not worth surfacing an error state
        // over; the notification simply stays unread until retried.
      }
    },
    [],
  );

  return (
    <View style={styles.flex}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <Text style={styles.title}>Notifications</Text>
      </View>

      {state.status === "loading" && (
        <View style={styles.centered}>
          <LoadingView label="Loading your notifications…" />
        </View>
      )}

      {state.status === "error" && (
        <View style={styles.centered} testID="notifications-error">
          <Text style={styles.errorText}>{state.message}</Text>
          <Button label="Retry" onPress={load} testID="notifications-retry-button" />
        </View>
      )}

      {state.status === "success" && state.notifications.length === 0 && (
        <View style={styles.centered} testID="notifications-empty">
          <Ionicons name="notifications-off-outline" size={48} color={colors.textMuted} />
          <Text style={styles.emptyText}>You&apos;re all caught up.</Text>
        </View>
      )}

      {state.status === "success" && state.notifications.length > 0 && (
        <FlatList
          testID="notifications-list"
          data={state.notifications}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.list}
          renderItem={({ item }) => (
            <Pressable
              onPress={() => void markRead(item)}
              style={[styles.row, !item.read_at && styles.rowUnread]}
              testID={`notification-${item.id}`}
              accessibilityRole="button"
            >
              <Ionicons name={ICONS[item.type]} size={22} color={colors.primary} />
              <View style={styles.rowBody}>
                <Text style={styles.rowTitle}>{item.title}</Text>
                <Text style={styles.rowBodyText}>{item.body}</Text>
              </View>
              {!item.read_at && <View style={styles.unreadDot} testID={`unread-dot-${item.id}`} />}
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  header: { padding: spacing.lg, paddingBottom: spacing.sm },
  title: { ...typography.title, color: colors.text },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
  errorText: { ...typography.body, color: colors.error, textAlign: "center" },
  emptyText: { ...typography.body, color: colors.textMuted },
  list: { padding: spacing.lg, gap: spacing.sm },
  row: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.md,
  },
  rowUnread: { borderColor: colors.primary },
  rowBody: { flex: 1, gap: 2 },
  rowTitle: { ...typography.subtitle, color: colors.text },
  rowBodyText: { ...typography.body, color: colors.textMuted },
  unreadDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.primary, marginTop: 6 },
});
