import React from "react";
import { StyleSheet, View, ViewProps } from "react-native";

import { colors, radius, shadow, spacing } from "../theme/tokens";

interface Props extends ViewProps {
  /** elevated (default): shadowed surface card. flat: no shadow, for
   * cards already inside another elevated container. */
  variant?: "elevated" | "flat";
}

export function Card({ style, children, variant = "elevated", ...rest }: Props): React.JSX.Element {
  return (
    <View
      style={[styles.card, variant === "elevated" && shadow.card, style]}
      {...rest}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
  },
});
