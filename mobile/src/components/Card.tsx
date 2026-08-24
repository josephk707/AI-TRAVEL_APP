import React from "react";
import { StyleSheet, View, ViewProps } from "react-native";

import { colors, radius, spacing } from "../theme/tokens";

export function Card({ style, children, ...rest }: ViewProps): React.JSX.Element {
  return (
    <View style={[styles.card, style]} {...rest}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.lg,
  },
});
