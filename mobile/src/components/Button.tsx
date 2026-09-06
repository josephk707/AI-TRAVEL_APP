import React from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { radius, spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";

interface Props {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
  testID?: string;
  /** primary: solid accent (black on white / white on black). secondary:
   * outlined on the page surface. ghost: text-only, for low-emphasis
   * actions inside a card. */
  variant?: "primary" | "secondary" | "ghost";
  icon?: React.ReactNode;
  fullWidth?: boolean;
}

export function Button({
  label,
  onPress,
  disabled,
  loading,
  testID,
  variant = "primary",
  icon,
  fullWidth = true,
}: Props): React.JSX.Element {
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);
  const isDisabled = disabled || loading;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!isDisabled }}
      onPress={onPress}
      disabled={isDisabled}
      testID={testID}
      style={({ pressed }) => [
        fullWidth && styles.fullWidth,
        styles.button,
        variant === "primary" && styles.primaryButton,
        variant === "secondary" && styles.secondaryButton,
        variant === "ghost" && styles.ghostButton,
        isDisabled && styles.disabled,
        pressed && !isDisabled && (variant === "primary" ? styles.primaryPressed : styles.pressed),
      ]}
    >
      <View style={styles.contentRow}>
        {loading ? (
          <ActivityIndicator
            size="small"
            color={variant === "primary" ? colors.primaryText : colors.text}
          />
        ) : (
          icon
        )}
        <Text
          style={[
            styles.label,
            variant === "primary" && styles.labelPrimary,
            variant === "secondary" && styles.labelSecondary,
            variant === "ghost" && styles.labelGhost,
          ]}
        >
          {label}
        </Text>
      </View>
    </Pressable>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    fullWidth: { width: "100%" },
    button: {
      minHeight: 48,
      paddingVertical: spacing.sm + 4,
      paddingHorizontal: spacing.lg,
      borderRadius: radius.md,
      alignItems: "center",
      justifyContent: "center",
    },
    primaryButton: { backgroundColor: colors.primary },
    primaryPressed: { backgroundColor: colors.primaryStrong, opacity: 0.9 },
    secondaryButton: {
      backgroundColor: colors.surface,
      borderWidth: 1,
      borderColor: colors.borderStrong,
    },
    ghostButton: {
      backgroundColor: "transparent",
      paddingHorizontal: spacing.sm,
      minHeight: 40,
    },
    contentRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
    pressed: { backgroundColor: colors.surfaceAlt },
    disabled: { opacity: 0.4 },
    label: { ...typography.subtitle },
    labelPrimary: { color: colors.primaryText },
    labelSecondary: { color: colors.text },
    labelGhost: { color: colors.text },
  });
