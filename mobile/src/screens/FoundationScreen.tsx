import React, { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";

import { ApiError } from "../api/client";
import { fetchBackendHealth, LivenessData } from "../api/health";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LoadingView } from "../components/LoadingView";
import { colors, spacing, typography } from "../theme/tokens";

type ConnectivityState =
  | { status: "loading" }
  | { status: "success"; data: LivenessData }
  | { status: "error"; message: string };

/**
 * Phase 1 foundation screen.
 *
 * Deliberately not a product screen — no trips, no AI, no maps (see
 * docs/PHASE_STATUS.md for what Phase 1 explicitly excludes). Its purpose
 * is to prove, with a real network call rather than a hardcoded value,
 * that the mobile app's navigation/theme/API-client/error-boundary/
 * loading-state foundation actually works end-to-end against the real
 * FastAPI backend built in this same phase.
 */
export function FoundationScreen(): React.JSX.Element {
  const [connectivity, setConnectivity] = useState<ConnectivityState>({ status: "loading" });

  // Only fires setState inside the .then/.catch microtask, never
  // synchronously in the caller's body — required so this can be called
  // directly from an effect without triggering cascading synchronous
  // renders (react-hooks/set-state-in-effect).
  const runHealthCheck = useCallback((signal?: AbortSignal) => {
    fetchBackendHealth(signal)
      .then((data) => setConnectivity({ status: "success", data }))
      .catch((error: unknown) => {
        const message =
          error instanceof ApiError
            ? error.message
            : "Unexpected error while checking backend connectivity.";
        setConnectivity({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    runHealthCheck(controller.signal);
    return () => controller.abort();
  }, [runHealthCheck]);

  // Safe to setState synchronously here — this runs inside an event
  // handler (the retry button's onPress), not inside an effect body.
  const handleRetry = useCallback(() => {
    setConnectivity({ status: "loading" });
    runHealthCheck();
  }, [runHealthCheck]);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <StatusBar style="auto" />
      <Text style={styles.title}>AI Tourist Guide</Text>
      <Text style={styles.subtitle}>Project Foundation — Phase 1</Text>

      <Card style={styles.card}>
        <Text style={styles.cardTitle}>Backend connectivity</Text>

        {connectivity.status === "loading" && <LoadingView label="Checking backend…" />}

        {connectivity.status === "success" && (
          <View testID="connectivity-success">
            <Text style={styles.successText}>Connected</Text>
            <Text style={styles.detail}>{connectivity.data.app_name}</Text>
            <Text style={styles.detail}>
              v{connectivity.data.app_version} · {connectivity.data.environment}
            </Text>
          </View>
        )}

        {connectivity.status === "error" && (
          <View testID="connectivity-error">
            <Text style={styles.errorText}>{connectivity.message}</Text>
            <Text style={styles.detail}>
              Start the backend (see README.md) and retry, or check EXPO_PUBLIC_API_BASE_URL in
              mobile/.env.
            </Text>
            <View style={styles.retryButton}>
              <Button label="Retry" onPress={handleRetry} testID="retry-button" />
            </View>
          </View>
        )}
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    backgroundColor: colors.background,
    padding: spacing.lg,
    gap: spacing.md,
  },
  title: { ...typography.title, color: colors.text },
  subtitle: { ...typography.body, color: colors.textMuted, marginBottom: spacing.md },
  card: { gap: spacing.sm },
  cardTitle: { ...typography.subtitle, color: colors.text },
  successText: { ...typography.subtitle, color: colors.success },
  errorText: { ...typography.subtitle, color: colors.error },
  detail: { ...typography.caption, color: colors.textMuted, marginTop: spacing.xs },
  retryButton: { marginTop: spacing.md, alignSelf: "flex-start" },
});
