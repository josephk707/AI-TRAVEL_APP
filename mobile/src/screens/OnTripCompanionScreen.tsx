import { Ionicons } from "@expo/vector-icons";
import { useRoute } from "@react-navigation/native";
import type { RouteProp } from "@react-navigation/native";
import * as Location from "expo-location";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { FlatList, Pressable, StyleSheet, Switch, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError } from "../api/client";
import {
  checkForDisruptions,
  DisruptionEvent,
  listDisruptions,
  resolveDisruption,
} from "../api/disruptions";
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
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingView } from "../components/LoadingView";
import { Screen } from "../components/Screen";
import { ScreenHeader } from "../components/ScreenHeader";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { radius, spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";

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
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);

  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [consent, setConsentState] = useState(false);
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [arrival, setArrival] = useState<ArrivalEvent | null>(null);
  const [nearby, setNearby] = useState<NearbyPoi[]>([]);
  const [checkingIn, setCheckingIn] = useState(false);
  const [disruptions, setDisruptions] = useState<DisruptionEvent[]>([]);
  const [checkingDisruptions, setCheckingDisruptions] = useState(false);
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

  const loadDisruptions = useCallback(() => {
    listDisruptions(tripId)
      .then((events) => setDisruptions(events.filter((e) => e.status === "proposed")))
      .catch(() => undefined);
  }, [tripId]);

  useEffect(() => {
    loadDisruptions();
  }, [loadDisruptions]);

  const checkNow = useCallback(async () => {
    setCheckingDisruptions(true);
    try {
      await checkForDisruptions(tripId);
      loadDisruptions();
    } catch {
      // A failed disruption check is not worth a screen-level error — the
      // traveller can simply try again, and the next automatic location
      // ping will also retry it.
    } finally {
      setCheckingDisruptions(false);
    }
  }, [tripId, loadDisruptions]);

  const resolveNow = useCallback(
    async (event: DisruptionEvent, decision: "accept" | "dismiss", alternativeIndex?: number) => {
      try {
        await resolveDisruption(tripId, event.id, decision, alternativeIndex);
        setDisruptions((prev) => prev.filter((e) => e.id !== event.id));
        if (decision === "accept") load();
      } catch {
        // Leave the card visible so the traveller can retry.
      }
    },
    [tripId, load],
  );

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
    <Screen>
      <View style={[styles.flex, { paddingTop: insets.top + spacing.sm }]}>
      <ScreenHeader title="On-trip companion" />

      <View style={styles.consentRow} testID="location-consent-row">
        <View style={styles.consentTextGroup}>
          <Text style={styles.consentLabel}>Share my location for this trip</Text>
          <Text style={styles.consentHint}>
            Detects when you arrive at a planned stop and suggests what&apos;s nearby.
          </Text>
        </View>
        <Switch
          value={consent}
          onValueChange={(v) => void toggleConsent(v)}
          trackColor={{ false: colors.surfaceHighlight, true: colors.primary }}
          thumbColor={consent ? colors.primaryText : colors.white}
          ios_backgroundColor={colors.surfaceHighlight}
          testID="location-consent-switch"
        />
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

      <View style={styles.disruptionsHeader}>
        <Text style={styles.sectionHeading}>Plan updates</Text>
        <Pressable onPress={() => void checkNow()} disabled={checkingDisruptions} testID="check-disruptions-button">
          <Text style={styles.checkNowText}>
            {checkingDisruptions ? "Checking…" : "Check now"}
          </Text>
        </Pressable>
      </View>

      {disruptions.map((event) => (
        <View key={event.id} style={styles.disruptionCard} testID={`disruption-${event.id}`}>
          <View style={styles.disruptionReasonRow}>
            <Ionicons name="alert-circle-outline" size={18} color={colors.warning} />
            <Text style={styles.disruptionReason}>{event.proposal.reason}</Text>
          </View>
          {event.proposal.alternatives.map((alt, index) => (
            <Pressable
              key={alt.poi_id}
              style={({ pressed }) => [styles.alternativeRow, pressed && styles.rowPressed]}
              onPress={() => void resolveNow(event, "accept", index)}
              testID={`accept-alternative-${event.id}-${index}`}
              accessibilityRole="button"
            >
              <Text style={styles.alternativeText}>Switch to {alt.poi_name}</Text>
              <Ionicons name="chevron-forward" size={16} color={colors.textFaint} />
            </Pressable>
          ))}
          <Pressable
            onPress={() => void resolveNow(event, "dismiss")}
            testID={`dismiss-disruption-${event.id}`}
          >
            <Text style={styles.dismissText}>Dismiss</Text>
          </Pressable>
        </View>
      ))}

      <Text style={[styles.sectionHeading, styles.remainingHeading]}>Remaining stops</Text>

      {state.status === "loading" && (
        <View style={styles.centered}>
          <LoadingView label="Loading your itinerary…" />
        </View>
      )}

      {state.status === "error" && (
        <View style={styles.centered} testID="on-trip-error">
          <ErrorState
            message={state.message}
            retryLabel="Retry"
            onRetry={load}
            testID="on-trip-retry-button"
          />
        </View>
      )}

      {state.status === "success" && state.items.length === 0 && (
        <View style={styles.centered} testID="on-trip-empty">
          <EmptyState icon="checkmark-done-outline" title="Every stop on this trip is complete." />
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
              style={({ pressed }) => [styles.stopRow, pressed && styles.rowPressed]}
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
    </Screen>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    flex: { flex: 1 },
    consentRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: spacing.sm,
      marginHorizontal: spacing.lg,
      backgroundColor: colors.surface,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.border,
      padding: spacing.md,
    },
    consentTextGroup: { flex: 1, gap: 2 },
    consentLabel: { ...typography.bodyMedium, color: colors.text },
    consentHint: { ...typography.caption, color: colors.textMuted },
    errorText: {
      ...typography.body,
      color: colors.error,
      textAlign: "center",
      marginHorizontal: spacing.lg,
      marginTop: spacing.sm,
    },
    actionsRow: { marginHorizontal: spacing.lg, marginTop: spacing.md, alignItems: "flex-start" },
    arrivalBanner: {
      flexDirection: "row",
      alignItems: "center",
      gap: spacing.sm,
      marginHorizontal: spacing.lg,
      marginTop: spacing.md,
      backgroundColor: colors.successSoft,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.success,
      padding: spacing.md,
    },
    arrivalText: { ...typography.bodyMedium, color: colors.success, flex: 1 },
    nearbySection: { marginHorizontal: spacing.lg, marginTop: spacing.md, gap: 2 },
    nearbyItem: { ...typography.caption, color: colors.textMuted, marginHorizontal: spacing.lg },
    disruptionsHeader: {
      flexDirection: "row",
      justifyContent: "space-between",
      alignItems: "center",
      marginHorizontal: spacing.lg,
      marginTop: spacing.md,
    },
    checkNowText: { ...typography.captionMedium, color: colors.text },
    disruptionCard: {
      marginHorizontal: spacing.lg,
      marginTop: spacing.sm,
      backgroundColor: colors.warningSoft,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.warning,
      padding: spacing.md,
      gap: spacing.sm,
    },
    disruptionReasonRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
    disruptionReason: { ...typography.bodyMedium, color: colors.text, flex: 1 },
    alternativeRow: {
      flexDirection: "row",
      justifyContent: "space-between",
      alignItems: "center",
      minHeight: 48,
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.border,
      borderRadius: radius.md,
      paddingVertical: spacing.sm,
      paddingHorizontal: spacing.md,
    },
    alternativeText: { ...typography.bodyMedium, color: colors.text, flex: 1 },
    dismissText: { ...typography.captionMedium, color: colors.textMuted, alignSelf: "flex-end" },
    rowPressed: { backgroundColor: colors.surfaceAlt },
    sectionHeading: { ...typography.subtitle, color: colors.text, marginHorizontal: spacing.lg },
    remainingHeading: { marginTop: spacing.md },
    centered: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      padding: spacing.xl,
      gap: spacing.sm,
    },
    list: { padding: spacing.lg, gap: spacing.sm },
    stopRow: {
      flexDirection: "row",
      justifyContent: "space-between",
      alignItems: "center",
      gap: spacing.sm,
      minHeight: 60,
      backgroundColor: colors.surface,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.border,
      padding: spacing.md,
    },
    stopName: { ...typography.subtitle, color: colors.text, flex: 1 },
    stopAction: {
      ...typography.captionMedium,
      color: colors.text,
      borderWidth: 1,
      borderColor: colors.borderStrong,
      borderRadius: radius.pill,
      paddingVertical: spacing.xs + 2,
      paddingHorizontal: spacing.md,
      overflow: "hidden",
    },
  });
