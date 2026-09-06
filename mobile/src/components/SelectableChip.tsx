import React from "react";
import { Pressable, StyleSheet, Text } from "react-native";

import { radius, spacing, type Theme, typography, useThemedStyles } from "../theme";

interface Props {
  label: string;
  selected: boolean;
  onPress: () => void;
  testID?: string;
}

/** Compact multi-select chip — used for the interest grid, where a dozen
 * full SelectableCards would make the screen too tall/scrolly for a quick
 * onboarding step. Selected chips invert (accent fill, accent foreground). */
export function SelectableChip({ label, selected, onPress, testID }: Props): React.JSX.Element {
  const styles = useThemedStyles(createStyles);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => [
        styles.chip,
        selected && styles.chipSelected,
        pressed && (selected ? styles.chipSelectedPressed : styles.chipPressed),
      ]}
    >
      <Text style={[styles.label, selected && styles.labelSelected]}>{label}</Text>
    </Pressable>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    chip: {
      paddingVertical: spacing.sm,
      paddingHorizontal: spacing.md,
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
    },
    chipSelected: { borderColor: colors.primary, backgroundColor: colors.primary },
    chipPressed: { backgroundColor: colors.surfaceAlt },
    chipSelectedPressed: { backgroundColor: colors.primaryStrong, opacity: 0.9 },
    label: { ...typography.body, color: colors.textMuted },
    labelSelected: { color: colors.primaryText, fontWeight: "600" },
  });
