import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, typography } from "../theme/tokens";
import { Button } from "./Button";

interface Props {
  icon?: keyof typeof Ionicons.glyphMap;
  title: string;
  message?: string;
  actionLabel?: string;
  onAction?: () => void;
  testID?: string;
}

/** Standard empty-state layout (CLAUDE.md §11) reused across every screen
 * instead of ad hoc per-screen markup, so "no data yet" always looks and
 * behaves the same way. */
export function EmptyState({
  icon = "compass-outline",
  title,
  message,
  actionLabel,
  onAction,
  testID,
}: Props): React.JSX.Element {
  return (
    <View style={styles.container} testID={testID ?? "empty-state"}>
      <View style={styles.iconBadge}>
        <Ionicons name={icon} size={28} color={colors.primary} />
      </View>
      <Text style={styles.title}>{title}</Text>
      {message ? <Text style={styles.message}>{message}</Text> : null}
      {actionLabel && onAction ? (
        <View style={styles.action}>
          <Button label={actionLabel} onPress={onAction} variant="secondary" fullWidth={false} />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
  iconBadge: {
    width: 64,
    height: 64,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xs,
  },
  title: { ...typography.h2, color: colors.text, textAlign: "center" },
  message: { ...typography.body, color: colors.textMuted, textAlign: "center" },
  action: { marginTop: spacing.sm },
});
