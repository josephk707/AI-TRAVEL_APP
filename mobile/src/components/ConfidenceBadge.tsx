import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { radius, spacing, type Theme, typography, useThemedStyles } from "../theme";

interface Props {
  confidence: "high" | "low";
  testID?: string;
}

/** Renders the AI confidence flag consistently everywhere a grounded
 * answer appears (MOBILE_ARCHITECTURE.md §10) — heritage narration (F8)
 * and visual Q&A (F9) today. A "low" flag always shows a plain-language
 * verify-locally disclaimer, never just a quiet badge (AI_ARCHITECTURE.md
 * §5.2.4/§6, FR-007/FR-008 business rule). */
export function ConfidenceBadge({ confidence, testID }: Props): React.JSX.Element | null {
  const styles = useThemedStyles(createStyles);
  if (confidence === "high") return null;
  return (
    <View style={styles.badge} testID={testID}>
      <Text style={styles.text}>⚠ Not fully verified — please confirm locally</Text>
    </View>
  );
}

// Semantic (warning) coloring is kept on purpose: this badge conveys AI
// confidence, which is status meaning, not decoration.
const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    badge: {
      backgroundColor: colors.warningSoft,
      borderRadius: radius.md,
      paddingVertical: spacing.xs,
      paddingHorizontal: spacing.sm,
      alignSelf: "flex-start",
    },
    text: { ...typography.caption, color: colors.warning, fontWeight: "600" },
  });
