import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback, useEffect, useState } from "react";
import { FlatList, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { StatusBar } from "expo-status-bar";

import { ApiError } from "../api/client";
import { listTrips, Trip } from "../api/trips";
import { Button } from "../components/Button";
import { LoadingView } from "../components/LoadingView";
import { TripCard } from "../components/TripCard";
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
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    listTrips()
      .then((trips) => {
        const sorted = [...trips].sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status]);
        setState({ status: "success", trips: sorted });
      })
      .catch((error: unknown) => {
        const message = error instanceof ApiError ? error.message : "Couldn't load your trips.";
        setState({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    const unsubscribe = navigation.addListener("focus", load);
    return unsubscribe;
  }, [navigation, load]);

  return (
    <View style={styles.container}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <Text style={styles.title}>Your trips</Text>
        <Button
          label="+ New trip"
          onPress={() => navigation.navigate("TripCreation")}
          testID="new-trip-button"
        />
      </View>

      {state.status === "loading" && <LoadingView label="Loading your trips…" />}

      {state.status === "error" && (
        <View style={styles.centered} testID="trips-error">
          <Text style={styles.errorText}>{state.message}</Text>
          <Button label="Retry" onPress={load} testID="trips-retry-button" />
        </View>
      )}

      {state.status === "success" && state.trips.length === 0 && (
        <View style={styles.centered} testID="trips-empty">
          <Ionicons name="map-outline" size={48} color={colors.textMuted} />
          <Text style={styles.emptyTitle}>No trips yet</Text>
          <Text style={styles.emptySubtitle}>
            Start a new trip and let Yatra AI plan it with you.
          </Text>
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
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    padding: spacing.lg,
  },
  title: { ...typography.title, color: colors.text },
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.sm },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
  errorText: { ...typography.body, color: colors.error, textAlign: "center" },
  emptyTitle: { ...typography.subtitle, color: colors.text, marginTop: spacing.sm },
  emptySubtitle: { ...typography.body, color: colors.textMuted, textAlign: "center" },
});
