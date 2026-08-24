import React from "react";
import { Pressable, StyleSheet, Text } from "react-native";

import { colors, radius, spacing, typography } from "../theme/tokens";

interface Props {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  testID?: string;
}

export function Button({ label, onPress, disabled, testID }: Props): React.JSX.Element {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      onPress={onPress}
      disabled={disabled}
      testID={testID}
      style={({ pressed }) => [
        styles.button,
        disabled && styles.disabled,
        pressed && !disabled && styles.pressed,
      ]}
    >
      <Text style={styles.label}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    backgroundColor: colors.primary,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
    alignItems: "center",
  },
  pressed: { opacity: 0.85 },
  disabled: { opacity: 0.5 },
  label: { ...typography.subtitle, color: colors.primaryText },
});
