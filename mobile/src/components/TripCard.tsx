import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import type { Trip } from "../api/trips";
import { useTranslation } from "../i18n";
import { colors, radius, spacing, typography } from "../theme/tokens";

const STATUS_COLOR: Record<Trip["status"], string> = {
  draft: colors.textMuted,
  upcoming: colors.primary,
  active: colors.success,
  completed: colors.textMuted,
  cancelled: colors.error,
};

interface Props {
  trip: Trip;
  onPress: () => void;
  testID?: string;
}

export function TripCard({ trip, onPress, testID }: Props): React.JSX.Element {
  const { t } = useTranslation();
  const dateLabel =
    trip.start_date && trip.end_date
      ? `${trip.start_date} → ${trip.end_date}`
      : t("trips.datesNotSet");
  const STATUS_LABEL: Record<Trip["status"], string> = {
    draft: t("trips.statusDraft"),
    upcoming: t("trips.statusUpcoming"),
    active: t("trips.statusActive"),
    completed: t("trips.statusCompleted"),
    cancelled: t("trips.statusCancelled"),
  };

  return (
    <Pressable
      accessibilityRole="button"
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
    >
      <View style={styles.iconBadge}>
        <Ionicons name="airplane-outline" size={22} color={colors.primaryText} />
      </View>
      <View style={styles.body}>
        <Text style={styles.title} numberOfLines={1}>
          {trip.title}
        </Text>
        <Text style={styles.destination} numberOfLines={1}>
          {trip.destination}
        </Text>
        <Text style={styles.date}>{dateLabel}</Text>
      </View>
      <View style={styles.statusColumn}>
        <Text style={[styles.status, { color: STATUS_COLOR[trip.status] }]}>
          {STATUS_LABEL[trip.status]}
        </Text>
        <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.md,
  },
  pressed: { opacity: 0.85 },
  iconBadge: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  body: { flex: 1, gap: 2 },
  title: { ...typography.subtitle, color: colors.text },
  destination: { ...typography.caption, color: colors.textMuted },
  date: { ...typography.caption, color: colors.textMuted },
  statusColumn: { alignItems: "flex-end", gap: spacing.xs },
  status: { ...typography.caption, fontWeight: "600" },
});
