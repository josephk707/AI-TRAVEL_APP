import React from "react";
import { StyleSheet, View } from "react-native";

import { spacing, type Theme, useThemedStyles } from "../theme";

interface Props {
  total: number;
  /** 0-indexed */
  currentIndex: number;
}

/** Step indicator for a short linear flow (onboarding's ≤6 screens,
 * MOBILE_ARCHITECTURE.md §2 / PRD Section 15 usability target) — gives the
 * user a sense of progress without a heavier stepper component. */
export function ProgressDots({ total, currentIndex }: Props): React.JSX.Element {
  const styles = useThemedStyles(createStyles);
  return (
    <View style={styles.row} accessibilityRole="progressbar" testID="onboarding-progress">
      {Array.from({ length: total }).map((_, index) => (
        <View
          key={index}
          style={[styles.dot, index === currentIndex ? styles.dotActive : styles.dotInactive]}
        />
      ))}
    </View>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    row: { flexDirection: "row", gap: spacing.xs, justifyContent: "center" },
    dot: { height: 6, borderRadius: 3 },
    dotActive: { width: 24, backgroundColor: colors.text },
    dotInactive: { width: 6, backgroundColor: colors.borderStrong },
  });
