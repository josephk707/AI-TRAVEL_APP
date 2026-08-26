import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import type { ItineraryItem } from "../api/trips";
import { colors, radius, spacing, typography } from "../theme/tokens";

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

export function ItineraryItemCard({ item, testID }: Props): React.JSX.Element {
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
            name={CATEGORY_ICON.other}
            size={16}
            color={colors.primary}
            style={styles.icon}
          />
          <Text style={styles.name} numberOfLines={2}>
            {item.poi_name ?? "Unassigned stop"}
          </Text>
        </View>
        {item.notes && <Text style={styles.notes}>{item.notes}</Text>}
        <View style={styles.badgeRow}>
          {item.estimated_cost != null && (
            <Text style={styles.badge}>₹{item.estimated_cost.toLocaleString()}</Text>
          )}
          {item.verify_on_arrival && (
            <Text style={[styles.badge, styles.badgeWarning]}>Verify hours on arrival</Text>
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
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
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
  icon: {},
  name: { ...typography.subtitle, color: colors.text, flexShrink: 1 },
  notes: { ...typography.caption, color: colors.textMuted },
  badgeRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, marginTop: spacing.xs },
  badge: {
    ...typography.caption,
    color: colors.text,
    backgroundColor: colors.background,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
    overflow: "hidden",
  },
  badgeWarning: { color: colors.warning },
  badgeWeather: { color: colors.warning },
  badgeSkipped: { color: colors.textMuted, textDecorationLine: "line-through" },
  weatherNote: { ...typography.caption, color: colors.warning, fontStyle: "italic" },
});
