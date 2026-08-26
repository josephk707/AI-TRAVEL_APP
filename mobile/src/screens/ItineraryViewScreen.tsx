import { useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { RouteProp } from "@react-navigation/native";
import React, { useCallback, useEffect, useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";

import { ApiError } from "../api/client";
import { fetchItinerary, fetchTrip, ItineraryDay, Trip } from "../api/trips";
import { ItineraryItemCard } from "../components/ItineraryItemCard";
import { LoadingView } from "../components/LoadingView";
import { Button } from "../components/Button";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { colors, radius, spacing, typography } from "../theme/tokens";

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

  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [refreshing, setRefreshing] = useState(false);

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
        message: err instanceof ApiError ? err.message : "Couldn't load this itinerary.",
      };
    }
  }, [tripId]);

  useEffect(() => {
    let cancelled = false;
    resolveItinerary().then((result) => {
      if (!cancelled) setState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [resolveItinerary]);

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

  if (state.status === "loading") {
    return (
      <View style={styles.centered}>
        <LoadingView label="Loading your itinerary…" />
      </View>
    );
  }

  if (state.status === "error") {
    return (
      <View style={styles.centered} testID="itinerary-error">
        <Text style={styles.errorText}>{state.message}</Text>
        <Button label="Retry" onPress={retryLoad} testID="itinerary-retry-button" />
      </View>
    );
  }

  const totalStops = state.days.reduce((sum, day) => sum + day.items.length, 0);

  return (
    <View style={styles.flex}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <Text style={styles.title}>{state.trip.title}</Text>
        <Text style={styles.subtitle}>{state.trip.destination}</Text>
      </View>

      {totalStops === 0 ? (
        <View style={styles.centered} testID="itinerary-empty">
          <Text style={styles.emptyText}>No itinerary items yet.</Text>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={refresh} />
          }
        >
          {state.days.map((day) => (
            <View key={day.day_number} style={styles.daySection}>
              <Text style={styles.dayHeading}>
                Day {day.day_number}
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
        style={styles.chatFab}
        onPress={() => navigation.navigate("Chat", { tripId })}
        testID="open-chat-fab"
        accessibilityRole="button"
      >
        <Text style={styles.chatFabText}>💬 Adjust plan</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
  errorText: { ...typography.body, color: colors.error, textAlign: "center" },
  emptyText: { ...typography.body, color: colors.textMuted },
  header: {
    padding: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  title: { ...typography.title, color: colors.text },
  subtitle: { ...typography.body, color: colors.textMuted },
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
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 3,
  },
  chatFabText: { ...typography.subtitle, color: colors.primaryText },
});
