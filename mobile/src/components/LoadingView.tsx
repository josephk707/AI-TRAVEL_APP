import React from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";

interface Props {
  label?: string;
}

/** Loading-state infrastructure (CLAUDE.md §11: every screen needs one). */
export function LoadingView({ label = "Loading…" }: Props): React.JSX.Element {
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);
  return (
    <View style={styles.container} testID="loading-view">
      <ActivityIndicator size="large" color={colors.text} />
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    container: { alignItems: "center", justifyContent: "center", gap: spacing.sm },
    label: { ...typography.caption, color: colors.textMuted },
  });
