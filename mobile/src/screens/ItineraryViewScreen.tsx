import { useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { RouteProp } from "@react-navigation/native";
import { Ionicons } from "@expo/vector-icons";
import * as FileSystem from "expo-file-system";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";

import { ApiError } from "../api/client";
import { fetchOfflinePackage } from "../api/offline";
import { fetchItinerary, fetchTrip, ItineraryDay, Trip } from "../api/trips";
import { ItineraryItemCard } from "../components/ItineraryItemCard";
import { ErrorState } from "../components/ErrorState";
import { EmptyState } from "../components/EmptyState";
import { LoadingView } from "../components/LoadingView";
import { Screen } from "../components/Screen";
import { ScreenHeader } from "../components/ScreenHeader";
import { useTranslation } from "../i18n";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { radius, spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";
import { useSafeAreaInsets } from "react-native-safe-area-context";

type LoadState =
  | { status: "loading" }
  | { status: "success"; trip: Trip; days: ItineraryDay[] }
  | { status: "error"; message: string };

/** F3/F12 — "map + timeline hybrid" itinerary view (MOBILE_ARCHITECTURE.md
 * §2/§3 ItineraryViewScreen). Map rendering itself is F6/F7 territory
 * (already built in Phase 5's ExploreScreen/PoiDetailScreen) — this screen
 * is the timeline half, with every AI-computed flag (verify_on_arrival,
 * weather_flag, budget) rendered visibly rather than silently applied. */
export function ItineraryViewScreen(): React.JSX.Element {
  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList, "ItineraryView">>();
  const route = useRoute<RouteProp<RootStackParamList, "ItineraryView">>();
  const { tripId } = route.params;
  const insets = useSafeAreaInsets();
  const { t } = useTranslation();
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);

  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadMessage, setDownloadMessage] = useState<string | null>(null);

  // Resolves the next LoadState without setting state itself (matches
  // PoiDetailScreen.tsx's resolveDetail/loadState split) so the mount
  // effect only ever calls setState inside a .then() callback.
  const resolveItinerary = useCallback(async (): Promise<LoadState> => {
    try {
      const [trip, days] = await Promise.all([fetchTrip(tripId), fetchItinerary(tripId)]);
      return { status: "success", trip, days };
    } catch (err) {
      return {
        status: "error",
        message: err instanceof ApiError ? err.message : t("itineraryView.couldntLoad"),
      };
    }
  }, [tripId, t]);

  useEffect(() => {
    let cancelled = false;
    resolveItinerary().then((result) => {
      if (!cancelled) setState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [resolveItinerary]);

  // Chat (F5) edits the plan while this screen stays mounted underneath
  // it, so a stale timeline would otherwise greet the traveller on the way
  // back. Re-fetch silently whenever the screen regains focus; the first
  // focus event (mount) is skipped because the effect above already loads.
  const initialFocusSeen = useRef(false);
  useEffect(() => {
    const unsubscribe = navigation.addListener?.("focus", () => {
      if (!initialFocusSeen.current) {
        initialFocusSeen.current = true;
        return;
      }
      void resolveItinerary().then((result) => {
        if (result.status === "success") setState(result);
      });
    });
    return unsubscribe;
  }, [navigation, resolveItinerary]);

  const retryLoad = useCallback(() => {
    setState({ status: "loading" });
    void resolveItinerary().then(setState);
  }, [resolveItinerary]);

  const refresh = useCallback(() => {
    setRefreshing(true);
    void resolveItinerary().then((result) => {
      setState(result);
      setRefreshing(false);
    });
  }, [resolveItinerary]);

  const downloadForOffline = useCallback(async () => {
    setDownloading(true);
    setDownloadMessage(null);
    try {
      const pkg = await fetchOfflinePackage(tripId);
      const directory = new FileSystem.Directory(FileSystem.Paths.document, "offline-packages");
      if (!directory.exists) directory.create({ intermediates: true });
      const file = new FileSystem.File(directory, `${tripId}.json`);
      if (!file.exists) file.create();
      file.write(JSON.stringify(pkg));
      setDownloadMessage(
        `Saved ${pkg.pois.length} place(s), ${pkg.heritage_content.length} heritage section(s), ` +
          `and ${pkg.phrasebook_entries.length} phrase(s) for offline use.`,
      );
    } catch (error) {
      setDownloadMessage(
        error instanceof ApiError ? error.message : t("itineraryView.couldntDownload"),
      );
    } finally {
      setDownloading(false);
    }
  }, [tripId, t]);

  if (state.status === "loading") {
    return (
      <Screen>
        <View style={styles.centered}>
          <LoadingView label={t("itineraryView.loading")} />
        </View>
      </Screen>
    );
  }

  if (state.status === "error") {
    return (
      <Screen>
        <View style={styles.centered} testID="itinerary-error">
          <ErrorState message={state.message} retryLabel={t("common.retry")} onRetry={retryLoad} testID="itinerary-retry-button" />
        </View>
      </Screen>
    );
  }

  const totalStops = state.days.reduce((sum, day) => sum + day.items.length, 0);

  return (
    <Screen>
      <View style={styles.flex}>
      <View style={{ paddingTop: insets.top + spacing.sm }}>
        <ScreenHeader title={state.trip.title} subtitle={state.trip.destination} />
      </View>
      <View style={styles.header}>
        <View style={styles.toolsRow}>
          <ToolButton
            icon="wallet-outline"
            label={t("itineraryView.budget")}
            testID="open-budget-button"
            onPress={() => navigation.navigate("BudgetView", { tripId })}
          />
          <ToolButton
            icon="images-outline"
            label={t("itineraryView.memories")}
            testID="open-memory-box-button"
            onPress={() => navigation.navigate("MemoryBox", { tripId })}
          />
          <ToolButton
            icon="chatbubbles-outline"
            label={t("itineraryView.phrases")}
            testID="open-phrasebook-button"
            onPress={() => navigation.navigate("Phrasebook", { tripId })}
          />
          <ToolButton
            icon="navigate-outline"
            label={t("itineraryView.onTrip")}
            testID="open-on-trip-companion-button"
            onPress={() => navigation.navigate("OnTripCompanion", { tripId })}
          />
          <ToolButton
            icon="people-outline"
            label={t("itineraryView.group")}
            testID="open-group-invite-button"
            onPress={() => navigation.navigate("GroupInvite", { tripId })}
          />
          <ToolButton
            icon="shield-checkmark-outline"
            label={t("itineraryView.safety")}
            testID="open-safety-button"
            onPress={() => navigation.navigate("Safety", { tripId })}
          />
          <ToolButton
            icon="cloud-download-outline"
            label={downloading ? t("itineraryView.saving") : t("itineraryView.offline")}
            testID="download-offline-button"
            onPress={() => void downloadForOffline()}
          />
        </View>
        {downloadMessage && (
          <Text style={styles.downloadMessage} testID="download-message">
            {downloadMessage}
          </Text>
        )}
      </View>

      {totalStops === 0 ? (
        <View style={styles.centered} testID="itinerary-empty">
          <EmptyState icon="map-outline" title={t("itineraryView.emptyItems")} />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.text} />
          }
        >
          {state.days.map((day) => (
            <View key={day.day_number} style={styles.daySection}>
              <Text style={styles.dayHeading}>
                {t("itineraryView.day")} {day.day_number}
                {day.date ? ` · ${day.date}` : ""}
              </Text>
              <View style={styles.dayItems}>
                {day.items.map((item) => (
                  <ItineraryItemCard key={item.id} item={item} testID={`item-${item.id}`} />
                ))}
              </View>
            </View>
          ))}
        </ScrollView>
      )}

      <Pressable
        style={({ pressed }) => [styles.chatFab, pressed && styles.chatFabPressed]}
        onPress={() => navigation.navigate("Chat", { tripId })}
        testID="open-chat-fab"
        accessibilityRole="button"
      >
        <Text style={styles.chatFabText}>💬 {t("itineraryView.adjustPlan")}</Text>
      </Pressable>
      </View>
    </Screen>
  );
}

function ToolButton({
  icon,
  label,
  onPress,
  testID,
}: {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  label: string;
  onPress: () => void;
  testID: string;
}): React.JSX.Element {
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);
  return (
    <Pressable
      style={({ pressed }) => [styles.toolButton, pressed && styles.toolButtonPressed]}
      onPress={onPress}
      accessibilityRole="button"
      testID={testID}
    >
      <Ionicons name={icon} size={20} color={colors.text} />
      <Text style={styles.toolButtonLabel}>{label}</Text>
    </Pressable>
  );
}

const createStyles = ({ colors, shadow }: Theme) =>
  StyleSheet.create({
    flex: { flex: 1 },
    centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
    header: {
      paddingHorizontal: spacing.lg,
      paddingBottom: spacing.md,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: colors.border,
    },
    toolsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
    toolButton: {
      alignItems: "center",
      gap: 2,
      minWidth: 64,
      paddingVertical: spacing.sm,
      paddingHorizontal: spacing.xs,
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.border,
      borderRadius: radius.md,
    },
    toolButtonPressed: { backgroundColor: colors.surfaceAlt },
    toolButtonLabel: { ...typography.caption, color: colors.textMuted },
    downloadMessage: { ...typography.caption, color: colors.textMuted, marginTop: spacing.sm },
    content: { padding: spacing.lg, gap: spacing.lg, paddingBottom: spacing.xl * 2 },
    daySection: { gap: spacing.sm },
    dayHeading: { ...typography.subtitle, color: colors.text },
    dayItems: { gap: spacing.sm },
    chatFab: {
      position: "absolute",
      right: spacing.lg,
      bottom: spacing.lg,
      backgroundColor: colors.primary,
      borderRadius: radius.lg,
      paddingVertical: spacing.sm + 2,
      paddingHorizontal: spacing.md,
      ...shadow.card,
    },
    chatFabPressed: { backgroundColor: colors.primaryStrong, opacity: 0.9 },
    chatFabText: { ...typography.subtitle, color: colors.primaryText },
  });
