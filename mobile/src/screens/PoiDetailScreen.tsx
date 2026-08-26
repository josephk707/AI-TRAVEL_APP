import { Ionicons } from "@expo/vector-icons";
import { useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { RouteProp } from "@react-navigation/native";
import React, { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import MapView, { Marker, PROVIDER_GOOGLE } from "react-native-maps";
import { StatusBar } from "expo-status-bar";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import type { Poi } from "../api/pois";
import { ApiError } from "../api/client";
import { fetchPoi } from "../api/pois";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LoadingView } from "../components/LoadingView";
import { MapErrorBoundary } from "../components/MapErrorBoundary";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { colors, radius, spacing, typography } from "../theme/tokens";

type LoadState =
  | { status: "loading" }
  | { status: "success"; poi: Poi }
  | { status: "error"; message: string };

const OPENING_HOURS_DAY_ORDER = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
];

function formatOpeningHours(hours: Record<string, unknown> | null): string[] {
  if (!hours) return [];
  const entries = Object.entries(hours).filter(([, value]) => typeof value === "string");
  if (entries.length === 0) return [];
  entries.sort(
    ([a], [b]) => OPENING_HOURS_DAY_ORDER.indexOf(a) - OPENING_HOURS_DAY_ORDER.indexOf(b),
  );
  return entries.map(([day, value]) => `${day[0].toUpperCase()}${day.slice(1)}: ${value}`);
}

/** F6 — Maps & Navigation. POI detail: address, category, opening hours
 * (when known — "verify on arrival" otherwise, matching FR-007's
 * exception-flow wording used elsewhere in this product for unconfirmed
 * hours), and a small map centered on the place. */
export function PoiDetailScreen(): React.JSX.Element {
  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList, "PoiDetail">>();
  const route = useRoute<RouteProp<RootStackParamList, "PoiDetail">>();
  const insets = useSafeAreaInsets();
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });

  // Resolves the next LoadState without setting state itself, so the
  // effect below can set state only inside a .then() callback
  // (react-hooks/set-state-in-effect) while the retry button — a real
  // event handler, not an effect — is free to set the "loading" state
  // synchronously before calling this (same split as
  // InterestSelectScreen.tsx's resolveInterests/loadInterests).
  const resolveDetail = useCallback(async (): Promise<LoadState> => {
    try {
      const poi = await fetchPoi(route.params.poiId);
      return { status: "success", poi };
    } catch (error) {
      return {
        status: "error",
        message: error instanceof ApiError ? error.message : "Couldn't load this place.",
      };
    }
  }, [route.params.poiId]);

  useEffect(() => {
    let cancelled = false;
    resolveDetail().then((result) => {
      if (!cancelled) setLoadState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [resolveDetail]);

  const retryLoad = useCallback(() => {
    setLoadState({ status: "loading" });
    void resolveDetail().then(setLoadState);
  }, [resolveDetail]);

  return (
    <View style={[styles.container, { paddingTop: insets.top + spacing.md }]}>
      <StatusBar style="dark" />

      {loadState.status === "loading" && (
        <View style={styles.centerFill}>
          <LoadingView label="Loading place…" />
        </View>
      )}

      {loadState.status === "error" && (
        <View style={styles.centerFill} testID="poi-detail-error">
          <Text style={styles.errorText}>{loadState.message}</Text>
          <View style={styles.retryButton}>
            <Button label="Retry" onPress={retryLoad} testID="poi-detail-retry-button" />
          </View>
        </View>
      )}

      {loadState.status === "success" && (
        <ScrollView contentContainerStyle={styles.scrollContent} testID="poi-detail-content">
          <MapErrorBoundary fallback={<View style={styles.mapFallback} />}>
            <MapView
              testID="poi-detail-map"
              style={styles.map}
              provider={PROVIDER_GOOGLE}
              initialRegion={{
                latitude: loadState.poi.location.lat,
                longitude: loadState.poi.location.lng,
                latitudeDelta: 0.02,
                longitudeDelta: 0.02,
              }}
            >
              <Marker
                coordinate={{
                  latitude: loadState.poi.location.lat,
                  longitude: loadState.poi.location.lng,
                }}
                title={loadState.poi.name}
              />
            </MapView>
          </MapErrorBoundary>

          <View style={styles.body}>
            <Text style={styles.name}>{loadState.poi.name}</Text>
            {loadState.poi.address && <Text style={styles.address}>{loadState.poi.address}</Text>}

            <Card style={styles.detailCard}>
              <DetailRow icon="pricetag-outline" label="Category">
                {loadState.poi.category}
              </DetailRow>
              {loadState.poi.avg_cost != null && (
                <DetailRow icon="wallet-outline" label="Typical cost">
                  ₹{loadState.poi.avg_cost}
                </DetailRow>
              )}
              <DetailRow icon="time-outline" label="Opening hours">
                {formatOpeningHours(loadState.poi.opening_hours).length > 0
                  ? formatOpeningHours(loadState.poi.opening_hours).join("\n")
                  : "Not confirmed — verify on arrival"}
              </DetailRow>
            </Card>

            {loadState.poi.category === "heritage" && (
              <Pressable
                style={({ pressed }) => [styles.heritageCard, pressed && styles.heritageCardPressed]}
                onPress={() =>
                  navigation.navigate("HeritageNarration", {
                    poiId: loadState.poi.id,
                    poiName: loadState.poi.name,
                  })
                }
                accessibilityRole="button"
                testID="heritage-story-button"
              >
                <Ionicons name="book-outline" size={20} color={colors.primaryText} />
                <Text style={styles.heritageCardText}>Read the heritage story</Text>
                <Ionicons name="chevron-forward" size={18} color={colors.primaryText} />
              </Pressable>
            )}
          </View>
        </ScrollView>
      )}
    </View>
  );
}

function DetailRow({
  icon,
  label,
  children,
}: {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  label: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <View style={styles.detailRow}>
      <Ionicons name={icon} size={18} color={colors.primary} />
      <View style={styles.detailTextGroup}>
        <Text style={styles.detailLabel}>{label}</Text>
        <Text style={styles.detailValue}>{children}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  centerFill: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl },
  errorText: { ...typography.body, color: colors.error, textAlign: "center" },
  retryButton: { marginTop: spacing.md },
  scrollContent: { paddingBottom: spacing.xl },
  map: { height: 220, width: "100%" },
  mapFallback: { height: 220, width: "100%", backgroundColor: colors.surface },
  body: { padding: spacing.lg, gap: spacing.sm },
  name: { ...typography.title, color: colors.text },
  address: { ...typography.body, color: colors.textMuted },
  detailCard: { gap: spacing.md, marginTop: spacing.sm },
  heritageCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.primary,
    borderRadius: radius.lg,
    padding: spacing.md,
    marginTop: spacing.md,
  },
  heritageCardPressed: { opacity: 0.85 },
  heritageCardText: { ...typography.subtitle, color: colors.primaryText, flex: 1 },
  detailRow: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start" },
  detailTextGroup: { flex: 1 },
  detailLabel: { ...typography.caption, color: colors.textMuted },
  detailValue: { ...typography.body, color: colors.text, textTransform: "capitalize" },
});
