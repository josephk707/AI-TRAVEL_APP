import { useRoute } from "@react-navigation/native";
import type { RouteProp } from "@react-navigation/native";
import React, { useCallback, useEffect, useState } from "react";
import { SectionList, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError } from "../api/client";
import { downloadTripPhrasebook, PhrasebookEntry } from "../api/phrasebook";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingView } from "../components/LoadingView";
import { Screen } from "../components/Screen";
import { ScreenHeader } from "../components/ScreenHeader";
import { useTranslation } from "../i18n";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { radius, spacing, type Theme, typography, useThemedStyles } from "../theme";

type LoadState =
  | { status: "loading" }
  | { status: "success"; entries: PhrasebookEntry[] }
  | { status: "error"; message: string };

function groupByCategory(entries: PhrasebookEntry[]): { title: string; data: PhrasebookEntry[] }[] {
  const groups = new Map<string, PhrasebookEntry[]>();
  for (const entry of entries) {
    const list = groups.get(entry.category) ?? [];
    list.push(entry);
    groups.set(entry.category, list);
  }
  return Array.from(groups.entries()).map(([title, data]) => ({ title, data }));
}

/** F10 — Local Phrase Assistant (static half). Real curated phrases tied
 * to the trip's own destination — never AI-generated (this is the fixed,
 * offline-downloadable baseline set, distinct from F-whatever's dynamic
 * translation). */
export function PhrasebookScreen(): React.JSX.Element {
  const route = useRoute<RouteProp<RootStackParamList, "Phrasebook">>();
  const { tripId } = route.params;
  const insets = useSafeAreaInsets();
  const { t } = useTranslation();
  const styles = useThemedStyles(createStyles);

  const [state, setState] = useState<LoadState>({ status: "loading" });

  const resolvePhrasebook = useCallback(async (): Promise<LoadState> => {
    try {
      const entries = await downloadTripPhrasebook(tripId);
      return { status: "success", entries };
    } catch (error) {
      return {
        status: "error",
        message: error instanceof ApiError ? error.message : t("phrasebook.couldntLoad"),
      };
    }
  }, [tripId, t]);

  useEffect(() => {
    let cancelled = false;
    resolvePhrasebook().then((result) => {
      if (!cancelled) setState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [resolvePhrasebook]);

  const load = useCallback(() => {
    setState({ status: "loading" });
    void resolvePhrasebook().then(setState);
  }, [resolvePhrasebook]);

  return (
    <Screen>
      <View style={styles.flex}>
        <View style={{ paddingTop: insets.top + spacing.sm }}>
          <ScreenHeader title={t("phrasebook.title")} />
        </View>

        {state.status === "loading" && (
          <View style={styles.centered}>
            <LoadingView label={t("phrasebook.loading")} />
          </View>
        )}

        {state.status === "error" && (
          <View style={styles.centered} testID="phrasebook-error">
            <ErrorState
              message={state.message}
              retryLabel={t("common.retry")}
              onRetry={load}
              testID="phrasebook-retry-button"
            />
          </View>
        )}

        {state.status === "success" && state.entries.length === 0 && (
          <View style={styles.centered} testID="phrasebook-empty">
            <EmptyState icon="chatbubbles-outline" title={t("phrasebook.emptyTitle")} />
          </View>
        )}

        {state.status === "success" && state.entries.length > 0 && (
          <SectionList
            testID="phrasebook-list"
            sections={groupByCategory(state.entries)}
            keyExtractor={(item) => item.id}
            contentContainerStyle={styles.list}
            renderSectionHeader={({ section }) => (
              <Text style={styles.sectionHeading}>{section.title}</Text>
            )}
            renderItem={({ item }) => (
              <View style={styles.phraseCard} testID={`phrase-${item.id}`}>
                <Text style={styles.phraseLocal}>{item.phrase_local_script}</Text>
                <Text style={styles.phraseEn}>{item.phrase_en}</Text>
                <Text style={styles.phraseTranslit}>{item.phrase_transliteration}</Text>
              </View>
            )}
          />
        )}
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
    list: { padding: spacing.lg, paddingTop: 0, gap: spacing.sm },
    sectionHeading: {
      ...typography.micro,
      color: colors.textMuted,
      textTransform: "uppercase",
      marginTop: spacing.md,
      marginBottom: spacing.xs,
    },
    phraseCard: {
      backgroundColor: colors.surface,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.border,
      padding: spacing.md,
      gap: 2,
      marginBottom: spacing.xs,
    },
    phraseLocal: { ...typography.subtitle, color: colors.text },
    phraseEn: { ...typography.body, color: colors.textMuted },
    phraseTranslit: { ...typography.caption, color: colors.textFaint },
  });
