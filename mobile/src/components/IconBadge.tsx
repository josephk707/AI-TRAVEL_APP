import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { StyleSheet, View } from "react-native";

import { radius, type Theme, useTheme, useThemedStyles } from "../theme";

interface Props {
  icon: keyof typeof Ionicons.glyphMap;
  size?: number;
  /** solid: neutral tinted square (default, for list rows).
   * inverse: filled accent circle — black on white / white on black —
   * for a screen's single hero action. */
  variant?: "solid" | "inverse";
}

export function IconBadge({ icon, size = 44, variant = "solid" }: Props): React.JSX.Element {
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);
  const iconSize = Math.round(size * 0.5);

  if (variant === "inverse") {
    return (
      <View style={[styles.badge, styles.inverseBadge, { width: size, height: size }]}>
        <Ionicons name={icon} size={iconSize} color={colors.primaryText} />
      </View>
    );
  }

  return (
    <View style={[styles.badge, styles.solidBadge, { width: size, height: size }]}>
      <Ionicons name={icon} size={iconSize} color={colors.text} />
    </View>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    badge: { alignItems: "center", justifyContent: "center" },
    solidBadge: {
      backgroundColor: colors.surfaceAlt,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
    },
    inverseBadge: { backgroundColor: colors.primary, borderRadius: radius.pill },
  });
