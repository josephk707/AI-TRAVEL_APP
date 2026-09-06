import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback, useEffect, useState } from "react";
import { FlatList, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError } from "../api/client";
import { listTrips, Trip } from "../api/trips";
import { BottomNavBar } from "../components/BottomNavBar";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { GradientBackground } from "../components/GradientBackground";
import { LoadingView } from "../components/LoadingView";
import { TripCard } from "../components/TripCard";
import { useTranslation } from "../i18n";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { colors, spacing, typography } from "../theme/tokens";

type LoadState =
  | { status: "loading" }
  | { status: "success"; trips: Trip[] }
  | { status: "error"; message: string };

const STATUS_ORDER: Record<Trip["status"], number> = {
  active: 0,
  upcoming: 1,
  draft: 2,
  completed: 3,
  cancelled: 4,
};

/** F12 — Trip Management (TripsListScreen, grouped upcoming/active/completed,
 * US-020). The entry point into the F3/F4/F5 core planning loop. */
export function TripsListScreen(): React.JSX.Element {
  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList, "TripsList">>();
  const insets = useSafeAreaInsets();
  const { t } = useTranslation();
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    listTrips()
      .then((trips) => {
        const sorted = [...trips].sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status]);
        setState({ status: "success", trips: sorted });
      })
      .catch((error: unknown) => {
        const message = error instanceof ApiError ? error.message : t("trips.couldntLoad");
        setState({ status: "error", message });
      });
  }, [t]);

  useEffect(() => {
    const unsubscribe = navigation.addListener("focus", load);
    return unsubscribe;
  }, [navigation, load]);

  return (
    <GradientBackground>
      <View style={[styles.container, { paddingTop: insets.top + spacing.sm }]}>
      <StatusBar style="light" />
      <View style={styles.header}>
        <Text style={styles.title}>{t("trips.title")}</Text>
        <Button
          label={`+ ${t("trips.newTrip")}`}
          onPress={() => navigation.navigate("TripCreation")}
          testID="new-trip-button"
          fullWidth={false}
        />
      </View>

      {state.status === "loading" && <LoadingView label={t("trips.loading")} />}

      {state.status === "error" && (
        <View style={styles.centered} testID="trips-error">
          <ErrorState message={state.message} retryLabel={t("common.retry")} onRetry={load} testID="trips-retry-button" />
        </View>
      )}

      {state.status === "success" && state.trips.length === 0 && (
        <View style={styles.centered} testID="trips-empty">
          <EmptyState icon="map-outline" title={t("trips.emptyTitle")} message={t("trips.emptySubtitle")} />
        </View>
      )}

      {state.status === "success" && state.trips.length > 0 && (
        <FlatList
          data={state.trips}
          keyExtractor={(trip) => trip.id}
          contentContainerStyle={styles.list}
          renderItem={({ item }) => (
            <TripCard
              trip={item}
              testID={`trip-card-${item.id}`}
              onPress={() =>
                navigation.navigate(
                  item.generation_status === "none" ? "Chat" : "ItineraryView",
                  { tripId: item.id },
                )
              }
            />
          )}
        />
      )}
      </View>
      <BottomNavBar active="TripsList" />
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    padding: spacing.lg,
  },
  title: { ...typography.title, color: colors.text },
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.sm, paddingBottom: spacing.xxl },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
});
