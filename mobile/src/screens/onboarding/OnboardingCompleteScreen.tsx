import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { ProgressDots } from "../../components/ProgressDots";
import {
  BUDGET_BRACKET_OPTIONS,
  PACE_OPTIONS,
  TRAVEL_STYLE_OPTIONS,
} from "../../onboarding/onboardingOptions";
import { useOnboardingStore } from "../../onboarding/onboardingStore";
import { useSubmitOnboarding } from "../../onboarding/useSubmitOnboarding";
import { colors, radius, spacing, typography } from "../../theme/tokens";

function labelFor<T extends string>(
  options: { value: T; label: string }[],
  value: T | null,
): string {
  return options.find((option) => option.value === value)?.label ?? "Not set";
}

/** Final onboarding screen: summary + the actual submit (POST
 * /onboarding/responses). On success, AuthContext's onboardingCompleted
 * flips true (via completeOnboardingLocally()) and RootNavigator swaps to
 * the authenticated app automatically — no explicit navigation call here. */
export function OnboardingCompleteScreen(): React.JSX.Element {
  const { interestIds, travelStyle, pace, budgetBracket } = useOnboardingStore();
  const { submit, state: submitState, errorMessage } = useSubmitOnboarding();
  const insets = useSafeAreaInsets();
  const isSubmitting = submitState === "submitting";

  return (
    <View style={[styles.container, { paddingTop: insets.top + spacing.md }]}>
      <StatusBar style="dark" />

      <View style={styles.header}>
        <ProgressDots total={4} currentIndex={3} />
      </View>

      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <View style={styles.hero}>
          <View style={styles.iconBadge}>
            <Ionicons name="checkmark-done" size={32} color={colors.primaryText} />
          </View>
          <Text style={styles.title}>You&apos;re all set</Text>
          <Text style={styles.subtitle}>
            Here&apos;s what we&apos;ll use to personalize your first trip.
          </Text>
        </View>

        <Card style={styles.summaryCard}>
          <SummaryRow
            icon="heart-outline"
            label="Interests"
            value={
              interestIds.length > 0
                ? `${interestIds.length} selected`
                : "None selected — we'll use popular picks"
            }
          />
          <SummaryRow
            icon="list-outline"
            label="Travel style"
            value={labelFor(TRAVEL_STYLE_OPTIONS, travelStyle)}
          />
          <SummaryRow icon="walk-outline" label="Pace" value={labelFor(PACE_OPTIONS, pace)} />
          <SummaryRow
            icon="wallet-outline"
            label="Budget"
            value={labelFor(BUDGET_BRACKET_OPTIONS, budgetBracket)}
          />
        </Card>

        {submitState === "error" && errorMessage && (
          <Text style={styles.errorText} testID="onboarding-submit-error">
            {errorMessage}
          </Text>
        )}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Button
          label={isSubmitting ? "" : submitState === "error" ? "Try again" : "Get started"}
          onPress={() => void submit()}
          disabled={isSubmitting}
          testID="onboarding-complete-button"
        />
        {isSubmitting && (
          <ActivityIndicator
            size="small"
            color={colors.primaryText}
            style={styles.buttonSpinner}
          />
        )}
      </View>
    </View>
  );
}

function SummaryRow({
  icon,
  label,
  value,
}: {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  label: string;
  value: string;
}): React.JSX.Element {
  return (
    <View style={styles.summaryRow}>
      <Ionicons name={icon} size={18} color={colors.primary} />
      <Text style={styles.summaryLabel}>{label}</Text>
      <Text style={styles.summaryValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  scrollContent: { padding: spacing.lg, gap: spacing.lg },
  hero: { alignItems: "center", gap: spacing.sm, paddingVertical: spacing.md },
  iconBadge: {
    width: 64,
    height: 64,
    borderRadius: radius.lg,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  title: { ...typography.title, color: colors.text, textAlign: "center" },
  subtitle: { ...typography.body, color: colors.textMuted, textAlign: "center" },
  summaryCard: { gap: spacing.sm },
  summaryRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  summaryLabel: { ...typography.body, color: colors.textMuted, flex: 1 },
  summaryValue: { ...typography.body, color: colors.text, fontWeight: "600" },
  errorText: { ...typography.body, color: colors.error, textAlign: "center" },
  footer: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  buttonSpinner: { position: "absolute", alignSelf: "center", top: spacing.sm + 4 },
});
