import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, typography } from "../theme/tokens";
import { Button } from "./Button";

interface Props {
  message: string;
  retryLabel?: string;
  onRetry?: () => void;
  testID?: string;
}

/** Standard error-state layout (CLAUDE.md §9/§11), paired with EmptyState —
 * every screen that can fail to load uses this same shape. */
export function ErrorState({
  message,
  retryLabel = "Retry",
  onRetry,
  testID,
}: Props): React.JSX.Element {
  return (
    <View style={styles.container} testID="error-state">
      <View style={styles.iconBadge}>
        <Ionicons name="alert-circle-outline" size={28} color={colors.error} />
      </View>
      <Text style={styles.message}>{message}</Text>
      {onRetry ? (
        <View style={styles.action}>
          <Button
            label={retryLabel}
            onPress={onRetry}
            variant="secondary"
            fullWidth={false}
            testID={testID}
          />
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
    backgroundColor: colors.errorSoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xs,
  },
  message: { ...typography.body, color: colors.text, textAlign: "center" },
  action: { marginTop: spacing.sm },
});
