import React from "react";
import { StyleSheet, View, ViewProps } from "react-native";

import { radius, spacing, type Theme, useThemedStyles } from "../theme";

interface Props extends ViewProps {
  /** elevated (default): bordered surface with a barely-there shadow in
   * light mode. flat: border only, for cards already inside another
   * container. */
  variant?: "elevated" | "flat";
}

export function Card({ style, children, variant = "elevated", ...rest }: Props): React.JSX.Element {
  const styles = useThemedStyles(createStyles);
  return (
    <View style={[styles.card, variant === "elevated" && styles.elevated, style]} {...rest}>
      {children}
    </View>
  );
}

const createStyles = ({ colors, shadow }: Theme) =>
  StyleSheet.create({
    card: {
      backgroundColor: colors.surface,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.border,
      padding: spacing.lg,
    },
    elevated: shadow.card,
  });
