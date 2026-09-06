import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { radius, spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";
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
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);

  return (
    <View style={styles.container} testID={testID ?? "empty-state"}>
      <View style={styles.iconBadge}>
        <Ionicons name={icon} size={26} color={colors.text} />
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

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    container: {
      alignItems: "center",
      justifyContent: "center",
      padding: spacing.xl,
      gap: spacing.sm,
    },
    iconBadge: {
      width: 60,
      height: 60,
      borderRadius: radius.pill,
      backgroundColor: colors.surfaceAlt,
      borderWidth: 1,
      borderColor: colors.border,
      alignItems: "center",
      justifyContent: "center",
      marginBottom: spacing.xs,
    },
    title: { ...typography.h2, color: colors.text, textAlign: "center" },
    message: { ...typography.body, color: colors.textMuted, textAlign: "center" },
    action: { marginTop: spacing.sm },
  });
