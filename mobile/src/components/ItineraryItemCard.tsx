import React, { useCallback, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import type { ItineraryItem } from "../api/trips";
import { openInMaps } from "../lib/maps";
import { radius, spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";

const CATEGORY_ICON: Record<string, React.ComponentProps<typeof Ionicons>["name"]> = {
  heritage: "business-outline",
  restaurant: "restaurant-outline",
  attraction: "star-outline",
  nature: "leaf-outline",
  shopping: "bag-outline",
  other: "location-outline",
};

interface Props {
  item: ItineraryItem;
  testID?: string;
}

/** One stop on the timeline. Every AI-computed flag is rendered visibly
 * (verify_on_arrival, weather_flag, and — AI-first itinerary phase — how
 * the location was obtained), and every stop is tappable into Google Maps
 * for navigation. */
export function ItineraryItemCard({ item, testID }: Props): React.JSX.Element {
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);
  const [navigateFailed, setNavigateFailed] = useState(false);

  const canNavigate = (item.lat != null && item.lng != null) || !!item.poi_name;

  const handleNavigate = useCallback(async () => {
    setNavigateFailed(false);
    const opened = await openInMaps(item);
    if (!opened) setNavigateFailed(true);
  }, [item]);

  return (
    <View style={styles.card} testID={testID}>
      <View style={styles.timeColumn}>
        <Text style={styles.time}>{item.planned_start ?? "--:--"}</Text>
        {item.estimated_duration_min && (
          <Text style={styles.duration}>{item.estimated_duration_min} min</Text>
        )}
      </View>
      <View style={styles.divider} />
      <View style={styles.body}>
        <View style={styles.titleRow}>
          <Ionicons
            name={CATEGORY_ICON[item.poi_category ?? "other"] ?? CATEGORY_ICON.other}
            size={16}
            color={colors.textMuted}
          />
          <Text style={styles.name} numberOfLines={2}>
            {item.poi_name ?? "Unassigned stop"}
          </Text>
        </View>
        {item.area ? <Text style={styles.area}>{item.area}</Text> : null}
        {item.notes && <Text style={styles.notes}>{item.notes}</Text>}
        <View style={styles.badgeRow}>
          {item.estimated_cost != null && (
            <Text style={styles.badge}>
              {item.estimated_cost === 0 ? "Free" : `₹${item.estimated_cost.toLocaleString()}`}
            </Text>
          )}
          {item.verify_on_arrival && (
            <Text style={[styles.badge, styles.badgeWarning]}>Verify hours on arrival</Text>
          )}
          {item.location_source === "ai_estimate" && (
            <Text style={[styles.badge, styles.badgeWarning]} testID={`${testID ?? "item"}-approx`}>
              Approximate location
            </Text>
          )}
          {item.location_source === "unresolved" && (
            <Text style={[styles.badge, styles.badgeWarning]} testID={`${testID ?? "item"}-unverified`}>
              Location not verified
            </Text>
          )}
          {item.weather_flag && (
            <Text style={[styles.badge, styles.badgeWeather]}>⛅ Weather alert</Text>
          )}
          {item.status === "skipped" && (
            <Text style={[styles.badge, styles.badgeSkipped]}>Skipped</Text>
          )}
        </View>
        {item.weather_flag && item.weather_alternative_suggestion && (
          <Text style={styles.weatherNote}>{item.weather_alternative_suggestion}</Text>
        )}
        {canNavigate && item.status !== "skipped" && (
          <Pressable
            onPress={() => void handleNavigate()}
            accessibilityRole="link"
            accessibilityLabel={`Navigate to ${item.poi_name ?? "this stop"}`}
            style={({ pressed }) => [styles.navigate, pressed && styles.navigatePressed]}
            testID={`${testID ?? "item"}-navigate`}
          >
            <Ionicons name="navigate-outline" size={14} color={colors.text} />
            <Text style={styles.navigateLabel}>Navigate</Text>
          </Pressable>
        )}
        {navigateFailed && (
          <Text style={styles.navigateError}>Couldn't open Maps on this device.</Text>
        )}
      </View>
    </View>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    card: {
      flexDirection: "row",
      backgroundColor: colors.surface,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.border,
      padding: spacing.md,
      gap: spacing.sm,
    },
    timeColumn: { width: 60, alignItems: "flex-start" },
    time: { ...typography.subtitle, color: colors.text },
    duration: { ...typography.caption, color: colors.textMuted },
    divider: { width: StyleSheet.hairlineWidth, backgroundColor: colors.border },
    body: { flex: 1, gap: spacing.xs, paddingLeft: spacing.sm },
    titleRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
    name: { ...typography.subtitle, color: colors.text, flexShrink: 1 },
    area: { ...typography.caption, color: colors.textFaint },
    notes: { ...typography.caption, color: colors.textMuted },
    badgeRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, marginTop: spacing.xs },
    badge: {
      ...typography.caption,
      color: colors.text,
      backgroundColor: colors.surfaceAlt,
      borderRadius: radius.sm,
      paddingHorizontal: spacing.xs,
      paddingVertical: 2,
      overflow: "hidden",
    },
    // Status-carrying badges only — everything else stays neutral.
    badgeWarning: { color: colors.warning, backgroundColor: colors.warningSoft },
    badgeWeather: { color: colors.warning, backgroundColor: colors.warningSoft },
    badgeSkipped: { color: colors.textMuted, textDecorationLine: "line-through" },
    weatherNote: { ...typography.caption, color: colors.warning, fontStyle: "italic" },
    navigate: {
      alignSelf: "flex-start",
      flexDirection: "row",
      alignItems: "center",
      gap: spacing.xs,
      marginTop: spacing.xs,
      paddingVertical: spacing.xs + 2,
      paddingHorizontal: spacing.sm + 2,
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: colors.borderStrong,
      backgroundColor: colors.surface,
    },
    navigatePressed: { backgroundColor: colors.surfaceAlt },
    navigateLabel: { ...typography.captionMedium, color: colors.text },
    navigateError: { ...typography.caption, color: colors.textMuted },
  });
