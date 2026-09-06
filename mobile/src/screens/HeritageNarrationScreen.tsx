import { useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { RouteProp } from "@react-navigation/native";
import React, { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError } from "../api/client";
import { fetchNarration, NarrationResult } from "../api/heritage";
import { Card } from "../components/Card";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import { ErrorState } from "../components/ErrorState";
import { LoadingView } from "../components/LoadingView";
import { Screen } from "../components/Screen";
import { ScreenHeader } from "../components/ScreenHeader";
import { useTranslation } from "../i18n";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { radius, spacing, type Theme, typography, useThemedStyles } from "../theme";

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
  const insets = useSafeAreaInsets();
  const { t } = useTranslation();
  const styles = useThemedStyles(createStyles);

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
        message: err instanceof ApiError ? err.message : t("heritageNarration.couldntLoad"),
      };
    }
  }, [poiId, t]);

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
    <Screen>
      <View style={styles.flex}>
        <View style={{ paddingTop: insets.top + spacing.sm }}>
          <ScreenHeader title={poiName} subtitle={t("heritageNarration.heritageStory")} />
        </View>

        {state.status === "loading" && (
          <View style={styles.centered}>
            <LoadingView label={t("heritageNarration.gatheringStory")} />
          </View>
        )}

        {state.status === "not_covered" && (
          <View style={styles.centered} testID="narration-not-covered">
            <Text style={styles.notCoveredText}>{t("heritageNarration.notCoveredMessage")}</Text>
          </View>
        )}

        {state.status === "error" && (
          <View style={styles.centered} testID="narration-error">
            <ErrorState
              message={state.message}
              retryLabel={t("common.retry")}
              onRetry={retryLoad}
              testID="narration-retry-button"
            />
          </View>
        )}

        {state.status === "success" && (
          <ScrollView contentContainerStyle={styles.content} testID="narration-content">
            <ConfidenceBadge confidence={state.result.confidence} testID="narration-confidence" />
            <Card style={styles.narrationCard}>
              <Text style={styles.narrationText}>{state.result.narration}</Text>
            </Card>
            <Text style={styles.sourcesLabel}>
              {t("heritageNarration.sourcedFrom")}: {state.result.sources.join(", ")}
            </Text>
          </ScrollView>
        )}

        <Pressable
          style={({ pressed }) => [styles.photoQaFab, pressed && styles.photoQaFabPressed]}
          onPress={() => navigation.navigate("PhotoQA", { poiId, poiName })}
          testID="open-photo-qa-fab"
          accessibilityRole="button"
        >
          <Text style={styles.photoQaFabText}>📷 {t("heritageNarration.askAboutPhoto")}</Text>
        </Pressable>
      </View>
    </Screen>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    flex: { flex: 1 },
    centered: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      padding: spacing.xl,
      gap: spacing.sm,
    },
    notCoveredText: { ...typography.body, color: colors.textMuted, textAlign: "center" },
    content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl * 2 },
    narrationCard: { gap: spacing.sm },
    narrationText: { ...typography.body, color: colors.text, lineHeight: 22 },
    sourcesLabel: { ...typography.caption, color: colors.textFaint },
    photoQaFab: {
      position: "absolute",
      right: spacing.lg,
      bottom: spacing.lg,
      backgroundColor: colors.primary,
      borderRadius: radius.md,
      paddingVertical: spacing.sm + 4,
      paddingHorizontal: spacing.md,
    },
    photoQaFabPressed: { backgroundColor: colors.primaryStrong, opacity: 0.9 },
    photoQaFabText: { ...typography.subtitle, color: colors.primaryText },
  });
