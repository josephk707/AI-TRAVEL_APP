import { useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { RouteProp } from "@react-navigation/native";
import React, { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";

import { ApiError } from "../api/client";
import { fetchNarration, NarrationResult } from "../api/heritage";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { LoadingView } from "../components/LoadingView";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { colors, radius, spacing, typography } from "../theme/tokens";

type LoadState =
  | { status: "loading" }
  | { status: "success"; result: NarrationResult }
  | { status: "not_covered" }
  | { status: "error"; message: string };

/** F8 — Heritage Narration RAG Pipeline. Real, grounded storytelling —
 * never a fabricated fact, always source-attributed, always visibly
 * flagged when confidence is low (AI_ARCHITECTURE.md §5.2). */
export function HeritageNarrationScreen(): React.JSX.Element {
  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList, "HeritageNarration">>();
  const route = useRoute<RouteProp<RootStackParamList, "HeritageNarration">>();
  const { poiId, poiName } = route.params;

  const [state, setState] = useState<LoadState>({ status: "loading" });

  const resolveNarration = useCallback(async (): Promise<LoadState> => {
    try {
      const result = await fetchNarration(poiId, "overview");
      return { status: "success", result };
    } catch (err) {
      if (err instanceof ApiError && err.code === "POI_NOT_COVERED") {
        return { status: "not_covered" };
      }
      return {
        status: "error",
        message: err instanceof ApiError ? err.message : "Couldn't load this story.",
      };
    }
  }, [poiId]);

  useEffect(() => {
    let cancelled = false;
    resolveNarration().then((result) => {
      if (!cancelled) setState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [resolveNarration]);

  const retryLoad = useCallback(() => {
    setState({ status: "loading" });
    void resolveNarration().then(setState);
  }, [resolveNarration]);

  return (
    <View style={styles.flex}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <Text style={styles.title}>{poiName}</Text>
        <Text style={styles.subtitle}>Heritage story</Text>
      </View>

      {state.status === "loading" && (
        <View style={styles.centered}>
          <LoadingView label="Gathering the story…" />
        </View>
      )}

      {state.status === "not_covered" && (
        <View style={styles.centered} testID="narration-not-covered">
          <Text style={styles.notCoveredText}>
            We do not have a verified story for this place yet — we never make one up.
          </Text>
        </View>
      )}

      {state.status === "error" && (
        <View style={styles.centered} testID="narration-error">
          <Text style={styles.errorText}>{state.message}</Text>
          <Button label="Retry" onPress={retryLoad} testID="narration-retry-button" />
        </View>
      )}

      {state.status === "success" && (
        <ScrollView contentContainerStyle={styles.content} testID="narration-content">
          <ConfidenceBadge confidence={state.result.confidence} testID="narration-confidence" />
          <Card style={styles.narrationCard}>
            <Text style={styles.narrationText}>{state.result.narration}</Text>
          </Card>
          <Text style={styles.sourcesLabel}>
            Sourced from: {state.result.sources.join(", ")}
          </Text>
        </ScrollView>
      )}

      <Pressable
        style={styles.photoQaFab}
        onPress={() => navigation.navigate("PhotoQA", { poiId, poiName })}
        testID="open-photo-qa-fab"
        accessibilityRole="button"
      >
        <Text style={styles.photoQaFabText}>📷 Ask about a photo</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  header: {
    padding: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  title: { ...typography.title, color: colors.text },
  subtitle: { ...typography.body, color: colors.textMuted },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
  errorText: { ...typography.body, color: colors.error, textAlign: "center" },
  notCoveredText: { ...typography.body, color: colors.textMuted, textAlign: "center" },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl * 2 },
  narrationCard: { gap: spacing.sm },
  narrationText: { ...typography.body, color: colors.text, lineHeight: 22 },
  sourcesLabel: { ...typography.caption, color: colors.textMuted },
  photoQaFab: {
    position: "absolute",
    right: spacing.lg,
    bottom: spacing.lg,
    backgroundColor: colors.primary,
    borderRadius: radius.lg,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.md,
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 3,
  },
  photoQaFabText: { ...typography.subtitle, color: colors.primaryText },
});
