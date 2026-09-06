import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import React from "react";
import { StyleSheet, View } from "react-native";

import { colors, gradients, radius } from "../theme/tokens";

interface Props {
  icon: keyof typeof Ionicons.glyphMap;
  size?: number;
  /** solid: flat tinted circle (default, for list rows).
   * gradient: violet gradient circle (for a screen's single hero action). */
  variant?: "solid" | "gradient";
}

export function IconBadge({ icon, size = 44, variant = "solid" }: Props): React.JSX.Element {
  const iconSize = Math.round(size * 0.5);
  const dimensionStyle = { width: size, height: size, borderRadius: size };

  if (variant === "gradient") {
    return (
      <LinearGradient
        colors={gradients.primaryButton}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={[styles.badge, dimensionStyle]}
      >
        <Ionicons name={icon} size={iconSize} color={colors.primaryText} />
      </LinearGradient>
    );
  }

  return (
    <View style={[styles.badge, styles.solidBadge, dimensionStyle]}>
      <Ionicons name={icon} size={iconSize} color={colors.primary} />
    </View>
  );
}

const styles = StyleSheet.create({
  badge: { alignItems: "center", justifyContent: "center" },
  solidBadge: { backgroundColor: colors.primarySoft, borderRadius: radius.md },
});
