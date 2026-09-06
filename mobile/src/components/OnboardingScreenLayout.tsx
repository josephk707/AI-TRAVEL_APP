import React from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";
import { Button } from "./Button";
import { ProgressDots } from "./ProgressDots";
import { Screen } from "./Screen";

const TOTAL_ONBOARDING_STEPS = 5;

interface Props {
  stepIndex: number;
  title: string;
  subtitle: string;
  onSkip: () => void;
  primaryLabel: string;
  onPrimaryPress: () => void;
  primaryBusy?: boolean;
  primaryTestID?: string;
  children: React.ReactNode;
}

/** Shared chrome for every onboarding screen — progress, skip affordance,
 * title/subtitle, scrollable content, and the primary CTA — so each screen
 * only implements its own question, not its own layout (MOBILE_ARCHITECTURE.md
 * §10's shared component-library principle). */
export function OnboardingScreenLayout({
  stepIndex,
  title,
  subtitle,
  onSkip,
  primaryLabel,
  onPrimaryPress,
  primaryBusy,
  primaryTestID,
  children,
}: Props): React.JSX.Element {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);

  return (
    <Screen>
      <View style={[styles.container, { paddingTop: insets.top + spacing.md }]}>
        <View style={styles.header}>
          <ProgressDots total={TOTAL_ONBOARDING_STEPS} currentIndex={stepIndex} />
          <Text
            accessibilityRole="button"
            onPress={onSkip}
            style={styles.skipLink}
            testID="onboarding-skip-link"
          >
            Skip
          </Text>
        </View>

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.subtitle}>{subtitle}</Text>
          <View style={styles.content}>{children}</View>
        </ScrollView>

        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
          <Button
            label={primaryBusy ? "" : primaryLabel}
            onPress={onPrimaryPress}
            disabled={primaryBusy}
            testID={primaryTestID}
          />
          {primaryBusy && (
            <ActivityIndicator
              size="small"
              color={colors.primaryText}
              style={styles.buttonSpinner}
            />
          )}
        </View>
      </View>
    </Screen>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    container: { flex: 1 },
    header: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      paddingHorizontal: spacing.lg,
      paddingBottom: spacing.sm,
    },
    skipLink: { ...typography.bodyMedium, color: colors.textMuted, padding: spacing.xs },
    scroll: { flex: 1 },
    scrollContent: { padding: spacing.lg, paddingTop: spacing.md, gap: spacing.md },
    title: { ...typography.title, color: colors.text },
    subtitle: { ...typography.body, color: colors.textMuted, marginBottom: spacing.sm },
    content: { gap: spacing.sm },
    footer: {
      paddingHorizontal: spacing.lg,
      paddingTop: spacing.md,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: colors.borderStrong,
    },
    buttonSpinner: { position: "absolute", alignSelf: "center", top: spacing.md + 14 },
  });
