import { LinearGradient } from "expo-linear-gradient";
import React from "react";
import { StyleSheet, View, ViewProps } from "react-native";

import { colors, gradients } from "../theme/tokens";

/** Shared screen backdrop — the deep indigo-violet hero gradient every
 * redesigned screen sits on, so the app reads as one product rather than
 * per-screen flat backgrounds. `variant="plain"` skips the gradient for
 * screens that need a solid base (e.g. behind a full-bleed map/image). */
export function GradientBackground({
  children,
  style,
  variant = "hero",
}: ViewProps & { variant?: "hero" | "plain" }): React.JSX.Element {
  if (variant === "plain") {
    return <View style={[styles.plain, style]}>{children}</View>;
  }
  return (
    <LinearGradient colors={gradients.hero} style={[styles.fill, style]}>
      {children}
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  plain: { flex: 1, backgroundColor: colors.background },
});
