import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, typography } from "../theme/tokens";

interface Props {
  title: string;
  subtitle?: string;
  /** Shows a circular back button that pops the current screen. Defaults
   * to true — pass false for a top-level tab screen with no "back". */
  showBack?: boolean;
  rightAction?: React.ReactNode;
}

/** Shared header for pushed/detail screens — a circular glass back
 * button + title, replacing each screen's previous ad hoc header markup. */
export function ScreenHeader({
  title,
  subtitle,
  showBack = true,
  rightAction,
}: Props): React.JSX.Element {
  const navigation = useNavigation();

  return (
    <View style={styles.row}>
      {showBack ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Back"
          onPress={() => navigation.goBack()}
          style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}
          testID="screen-header-back"
        >
          <Ionicons name="chevron-back" size={22} color={colors.text} />
        </Pressable>
      ) : (
        <View style={styles.iconButtonSpacer} />
      )}

      <View style={styles.titleGroup}>
        <Text style={styles.title} numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text style={styles.subtitle} numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </View>

      {rightAction ?? <View style={styles.iconButtonSpacer} />}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  iconButton: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceAlt,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  iconButtonSpacer: { width: 40, height: 40 },
  pressed: { opacity: 0.7 },
  titleGroup: { flex: 1 },
  title: { ...typography.h1, color: colors.text },
  subtitle: { ...typography.caption, color: colors.textMuted, marginTop: 2 },
});
