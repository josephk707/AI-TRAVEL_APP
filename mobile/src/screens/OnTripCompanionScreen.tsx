import { Ionicons } from "@expo/vector-icons";
import { useRoute } from "@react-navigation/native";
import type { RouteProp } from "@react-navigation/native";
import * as Location from "expo-location";
import { StatusBar } from "expo-status-bar";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { FlatList, Pressable, StyleSheet, Switch, Text, View } from "react-native";

import { ApiError } from "../api/client";
import {
  ArrivalEvent,
  fetchNearby,
  NearbyPoi,
  setLocationConsent,
  submitLocationPing,
  submitManualLocation,
} from "../api/location";
import { fetchItinerary, ItineraryItem } from "../api/trips";
import { Button } from "../components/Button";
import { LoadingView } from "../components/LoadingView";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { colors, radius, spacing, typography } from "../theme/tokens";

type LoadState =
  | { status: "loading" }
  | { status: "success"; items: ItineraryItem[] }
  | { status: "error"; message: string };

const WATCH_INTERVAL_MS = 60_000;

/** F7 — Real-Time Location Companion & Arrival Notifications. Location
 * sharing is OFF by default and gated by explicit per-trip consent
 * (BR-014) — no ping is ever sent before the traveller flips the switch
 * below. FR-006's manual fallback (GPS denied/unavailable) never needs
 * consent, since it involves no GPS write at all. */
export function OnTripCompanionScreen(): React.JSX.Element {
  const route = useRoute<RouteProp<RootStackParamList, "OnTripCompanion">>();
  const { tripId } = route.params;

  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [consent, setConsentState] = useState(false);
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [arrival, setArrival] = useState<ArrivalEvent | null>(null);
  const [nearby, setNearby] = useState<NearbyPoi[]>([]);
  const [checkingIn, setCheckingIn] = useState(false);
  const watchSubscription = useRef<Location.LocationSubscription | null>(null);

  const resolveItinerary = useCallback(async (): Promise<LoadState> => {
    try {
      const days = await fetchItinerary(tripId);
      const items = days.flatMap((day) => day.items).filter((item) => item.status !== "completed");
      return { status: "success", items };
    } catch (error) {
      return {
        status: "error",
        message: error instanceof ApiError ? error.message : "Couldn't load your itinerary.",
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

  const load = useCallback(() => {
    setState({ status: "loading" });
    void resolveItinerary().then(setState);
  }, [resolveItinerary]);

  useEffect(() => {
    return () => {
      watchSubscription.current?.remove();
    };
  }, []);

  const pingNow = useCallback(
    async (lat: number, lng: number) => {
      try {
        const result = await submitLocationPing(tripId, lat, lng);
        if (result.arrival_event) {
          setArrival(result.arrival_event);
          load();
        }
        setNearby(result.nearby);
      } catch {
        // A single missed ping is not worth surfacing as a screen-level
        // error — the next automatic ping, or a manual check-in, retries.
      }
    },
    [tripId, load],
  );

  const startWatching = useCallback(async () => {
    const permission = await Location.requestForegroundPermissionsAsync();
    if (!permission.granted) {
      setPermissionError("Location access is needed to track arrivals automatically.");
      return;
    }
    watchSubscription.current?.remove();
    watchSubscription.current = await Location.watchPositionAsync(
      { accuracy: Location.Accuracy.Balanced, timeInterval: WATCH_INTERVAL_MS, distanceInterval: 50 },
      (position) => {
        void pingNow(position.coords.latitude, position.coords.longitude);
      },
    );
  }, [pingNow]);

  const toggleConsent = useCallback(
    async (value: boolean) => {
      setPermissionError(null);
      try {
        await setLocationConsent(tripId, value);
        setConsentState(value);
        if (value) {
          void startWatching();
        } else {
          watchSubscription.current?.remove();
          watchSubscription.current = null;
        }
      } catch (error) {
        setPermissionError(error instanceof ApiError ? error.message : "Couldn't update location sharing.");
      }
    },
    [tripId, startWatching],
  );

  const checkInNow = useCallback(async () => {
    setCheckingIn(true);
    setPermissionError(null);
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (!permission.granted) {
        setPermissionError("Location access is needed to check in.");
        return;
      }
      const position = await Location.getCurrentPositionAsync({});
      await pingNow(position.coords.latitude, position.coords.longitude);
      const nearbyResult = await fetchNearby(
        tripId,
        position.coords.latitude,
        position.coords.longitude,
      );
      setNearby(nearbyResult);
    } catch (error) {
      setPermissionError(error instanceof ApiError ? error.message : "Couldn't check your location.");
    } finally {
      setCheckingIn(false);
    }
  }, [tripId, pingNow]);

  const confirmArrivalManually = useCallback(
    async (item: ItineraryItem) => {
      if (!item.poi_id) return;
      try {
        const result = await submitManualLocation(tripId, item.poi_id);
        if (result.arrival_event) {
          setArrival(result.arrival_event);
          load();
        }
      } catch (error) {
        setPermissionError(
          error instanceof ApiError ? error.message : "Couldn't confirm your arrival.",
        );
      }
    },
    [tripId, load],
  );

  return (
    <View style={styles.flex}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <Text style={styles.title}>On-trip companion</Text>
      </View>

      <View style={styles.consentRow} testID="location-consent-row">
        <View style={styles.consentTextGroup}>
          <Text style={styles.consentLabel}>Share my location for this trip</Text>
          <Text style={styles.consentHint}>
            Detects when you arrive at a planned stop and suggests what&apos;s nearby.
          </Text>
        </View>
        <Switch value={consent} onValueChange={(v) => void toggleConsent(v)} testID="location-consent-switch" />
      </View>

      {permissionError && (
        <Text style={styles.errorText} testID="location-permission-error">
          {permissionError}
        </Text>
      )}

      <View style={styles.actionsRow}>
        <Button
          label={checkingIn ? "Checking in…" : "Check in now"}
          onPress={() => void checkInNow()}
          disabled={checkingIn || !consent}
          testID="check-in-button"
        />
      </View>

      {arrival && (
        <View style={styles.arrivalBanner} testID="arrival-banner">
          <Ionicons name="checkmark-circle-outline" size={20} color={colors.success} />
          <Text style={styles.arrivalText}>You&apos;ve arrived at {arrival.poi_name}!</Text>
        </View>
      )}

      {nearby.length > 0 && (
        <View style={styles.nearbySection} testID="nearby-section">
          <Text style={styles.sectionHeading}>Nearby</Text>
          {nearby.map((poi) => (
            <Text key={poi.poi_id} style={styles.nearbyItem}>
              {poi.name} · {Math.round(poi.distance_m)}m away
            </Text>
          ))}
        </View>
      )}

      <Text style={[styles.sectionHeading, styles.remainingHeading]}>Remaining stops</Text>

      {state.status === "loading" && (
        <View style={styles.centered}>
          <LoadingView label="Loading your itinerary…" />
        </View>
      )}

      {state.status === "error" && (
        <View style={styles.centered} testID="on-trip-error">
          <Text style={styles.errorText}>{state.message}</Text>
          <Button label="Retry" onPress={load} testID="on-trip-retry-button" />
        </View>
      )}

      {state.status === "success" && state.items.length === 0 && (
        <View style={styles.centered} testID="on-trip-empty">
          <Text style={styles.emptyText}>Every stop on this trip is complete.</Text>
        </View>
      )}

      {state.status === "success" && state.items.length > 0 && (
        <FlatList
          testID="remaining-stops-list"
          data={state.items}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.list}
          renderItem={({ item }) => (
            <Pressable
              style={styles.stopRow}
              onPress={() => void confirmArrivalManually(item)}
              testID={`manual-arrival-${item.id}`}
              accessibilityRole="button"
            >
              <Text style={styles.stopName}>{item.poi_name ?? "Custom stop"}</Text>
              <Text style={styles.stopAction}>I&apos;m here</Text>
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
  consentRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginHorizontal: spacing.lg,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.md,
  },
  consentTextGroup: { flex: 1, gap: 2 },
  consentLabel: { ...typography.body, color: colors.text },
  consentHint: { ...typography.caption, color: colors.textMuted },
  errorText: { ...typography.body, color: colors.error, textAlign: "center", marginHorizontal: spacing.lg, marginTop: spacing.sm },
  actionsRow: { marginHorizontal: spacing.lg, marginTop: spacing.md, alignItems: "flex-start" },
  arrivalBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    marginHorizontal: spacing.lg,
    marginTop: spacing.md,
    backgroundColor: "#E3F5EC",
    borderRadius: radius.sm,
    padding: spacing.sm,
  },
  arrivalText: { ...typography.body, color: colors.success },
  nearbySection: { marginHorizontal: spacing.lg, marginTop: spacing.md, gap: 2 },
  nearbyItem: { ...typography.caption, color: colors.textMuted },
  sectionHeading: { ...typography.subtitle, color: colors.text, marginHorizontal: spacing.lg },
  remainingHeading: { marginTop: spacing.md },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
  emptyText: { ...typography.body, color: colors.textMuted },
  list: { padding: spacing.lg, gap: spacing.sm },
  stopRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.md,
  },
  stopName: { ...typography.body, color: colors.text, flex: 1 },
  stopAction: { ...typography.caption, color: colors.primary },
});
