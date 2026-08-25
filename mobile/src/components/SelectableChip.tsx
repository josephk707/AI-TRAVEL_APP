import React from "react";
import { Pressable, StyleSheet, Text } from "react-native";

import { colors, radius, spacing, typography } from "../theme/tokens";

interface Props {
  label: string;
  selected: boolean;
  onPress: () => void;
  testID?: string;
}

/** Compact multi-select chip — used for the interest grid, where a dozen
 * full SelectableCards would make the screen too tall/scrolly for a quick
 * onboarding step. */
export function SelectableChip({ label, selected, onPress, testID }: Props): React.JSX.Element {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => [
        styles.chip,
        selected && styles.chipSelected,
        pressed && styles.chipPressed,
      ]}
    >
      <Text style={[styles.label, selected && styles.labelSelected]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  chipSelected: { borderColor: colors.primary, backgroundColor: colors.primary },
  chipPressed: { opacity: 0.8 },
  label: { ...typography.body, color: colors.text },
  labelSelected: { color: colors.primaryText, fontWeight: "600" },
});
