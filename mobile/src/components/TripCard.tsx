import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import type { Trip } from "../api/trips";
import { useTranslation } from "../i18n";
import {
  radius,
  spacing,
  type Theme,
  type ThemeColors,
  typography,
  useTheme,
  useThemedStyles,
} from "../theme";

/** Status text color — resolved against the active palette. Only
 * active/cancelled carry semantic color (status meaning); the rest stay
 * monochrome. */
function statusColor(colors: ThemeColors): Record<Trip["status"], string> {
  return {
    draft: colors.textMuted,
    upcoming: colors.text,
    active: colors.success,
    completed: colors.textMuted,
    cancelled: colors.error,
  };
}

interface Props {
  trip: Trip;
  onPress: () => void;
  testID?: string;
}

export function TripCard({ trip, onPress, testID }: Props): React.JSX.Element {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);
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
        <Ionicons name="airplane-outline" size={22} color={colors.text} />
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
        <Text style={[styles.status, { color: statusColor(colors)[trip.status] }]}>
          {STATUS_LABEL[trip.status]}
        </Text>
        <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
      </View>
    </Pressable>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    card: {
      flexDirection: "row",
      alignItems: "center",
      gap: spacing.sm,
      backgroundColor: colors.surface,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.border,
      padding: spacing.md,
    },
    pressed: { backgroundColor: colors.surfaceAlt },
    iconBadge: {
      width: 44,
      height: 44,
      borderRadius: radius.md,
      backgroundColor: colors.surfaceAlt,
      borderWidth: 1,
      borderColor: colors.border,
      alignItems: "center",
      justifyContent: "center",
    },
    body: { flex: 1, gap: 2 },
    title: { ...typography.subtitle, color: colors.text },
    destination: { ...typography.caption, color: colors.textMuted },
    date: { ...typography.caption, color: colors.textFaint },
    statusColumn: { alignItems: "flex-end", gap: spacing.xs },
    status: { ...typography.caption, fontWeight: "600" },
  });
