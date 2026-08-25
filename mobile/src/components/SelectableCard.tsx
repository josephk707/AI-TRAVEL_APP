import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, typography } from "../theme/tokens";

interface Props {
  label: string;
  description?: string;
  icon?: React.ComponentProps<typeof Ionicons>["name"];
  selected: boolean;
  onPress: () => void;
  testID?: string;
}

/**
 * A single selectable option card — used for both single-select (pace,
 * travel style, budget bracket) and multi-select (interests) questions;
 * the caller decides selection semantics (radio vs. checkbox), this
 * component only renders the visual selected/unselected state and reports
 * taps.
 */
export function SelectableCard({
  label,
  description,
  icon,
  selected,
  onPress,
  testID,
}: Props): React.JSX.Element {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        selected && styles.cardSelected,
        pressed && styles.cardPressed,
      ]}
    >
      {icon && (
        <View style={[styles.iconBadge, selected && styles.iconBadgeSelected]}>
          <Ionicons name={icon} size={20} color={selected ? colors.primaryText : colors.primary} />
        </View>
      )}
      <View style={styles.textColumn}>
        <Text style={[styles.label, selected && styles.labelSelected]}>{label}</Text>
        {description && <Text style={styles.description}>{description}</Text>}
      </View>
      {selected && (
        <Ionicons name="checkmark-circle" size={22} color={colors.primary} style={styles.check} />
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1.5,
    borderColor: colors.border,
    padding: spacing.md,
    gap: spacing.md,
  },
  cardSelected: {
    borderColor: colors.primary,
    backgroundColor: "#EAF5F1",
  },
  cardPressed: { opacity: 0.85 },
  iconBadge: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    backgroundColor: colors.background,
    alignItems: "center",
    justifyContent: "center",
  },
  iconBadgeSelected: { backgroundColor: colors.primary },
  textColumn: { flex: 1, gap: 2 },
  label: { ...typography.subtitle, color: colors.text },
  labelSelected: { color: colors.text, fontWeight: "700" },
  description: { ...typography.caption, color: colors.textMuted },
  check: { marginLeft: spacing.xs },
});
