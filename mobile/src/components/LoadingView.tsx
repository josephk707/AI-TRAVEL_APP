import React from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { colors, spacing, typography } from "../theme/tokens";

interface Props {
  label?: string;
}

/** Loading-state infrastructure (CLAUDE.md §11: every screen needs one). */
export function LoadingView({ label = "Loading…" }: Props): React.JSX.Element {
  return (
    <View style={styles.container} testID="loading-view">
      <ActivityIndicator size="large" color={colors.primary} />
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: "center", justifyContent: "center", gap: spacing.sm },
  label: { ...typography.caption, color: colors.textMuted },
});
