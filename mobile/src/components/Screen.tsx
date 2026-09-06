import React from "react";
import { StyleSheet, View, ViewProps } from "react-native";

import { layout, useTheme } from "../theme";

interface Props extends ViewProps {
  /** Width of the centred content column on wide viewports (tablets,
   * desktop browsers). Phones always get the full width. Pass
   * `"full"` for screens that should stay edge-to-edge (full-bleed
   * maps). Defaults to the reading-width column. */
  maxWidth?: number | "full";
}

/** Shared screen backdrop — a flat page in the active theme's background
 * colour (white in light mode, black in dark mode) that centres its
 * content in a max-width column once the viewport is wider than a phone,
 * so the same screens read well on a tablet or in a browser instead of
 * stretching edge to edge. */
export function Screen({
  children,
  style,
  maxWidth = layout.contentMaxWidth,
  ...rest
}: Props): React.JSX.Element {
  const { colors } = useTheme();
  return (
    <View style={[styles.page, { backgroundColor: colors.background }]} {...rest}>
      <View style={[styles.column, maxWidth !== "full" && { maxWidth }, style]}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1 },
  column: { flex: 1, width: "100%", alignSelf: "center" },
});
