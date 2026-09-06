import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";

import { OnboardingScreenLayout } from "../../components/OnboardingScreenLayout";
import { SelectableCard } from "../../components/SelectableCard";
import type { OnboardingStackParamList } from "../../navigation/OnboardingNavigator";
import { COMPANION_OPTIONS } from "../../onboarding/onboardingOptions";
import { useOnboardingStore } from "../../onboarding/onboardingStore";
import { useSubmitOnboarding } from "../../onboarding/useSubmitOnboarding";
import { colors, radius, spacing, typography } from "../../theme/tokens";

const MOTIVATION_MAX_LENGTH = 500;

/**
 * Final Personalization phase (Part 3): the 5th/6th onboarding question —
 * who the traveller usually travels with (single-select, matches
 * profiles.travel_companion) plus one open-ended conversational question
 * ("What makes a trip special for you?", matches profiles.trip_motivation,
 * capped at 500 chars server-side — see backend/app/schemas/onboarding.py).
 * Both optional, like every other onboarding question.
 */
export function TravelMotivationScreen(): React.JSX.Element {
  const navigation =
    useNavigation<NativeStackNavigationProp<OnboardingStackParamList, "TravelMotivation">>();
  const { travelCompanion, tripMotivation, setTravelCompanion, setTripMotivation } =
    useOnboardingStore();
  const { submit, state: submitState, errorMessage: submitError } = useSubmitOnboarding();

  const handleSkip = useCallback(async () => {
    await submit();
  }, [submit]);

  return (
    <OnboardingScreenLayout
      stepIndex={3}
      title="One more thing"
      subtitle="Both are optional — this helps us make your itineraries feel personal."
      onSkip={handleSkip}
      primaryLabel="Continue"
      onPrimaryPress={() => navigation.navigate("OnboardingComplete")}
      primaryBusy={submitState === "submitting"}
      primaryTestID="travel-motivation-continue-button"
    >
      <Text style={styles.sectionLabel}>Who do you usually travel with?</Text>
      <View style={styles.optionGroup} testID="travel-companion-options">
        {COMPANION_OPTIONS.map((option) => (
          <SelectableCard
            key={option.value}
            label={option.label}
            description={option.description}
            icon={option.icon}
            selected={travelCompanion === option.value}
            onPress={() => setTravelCompanion(option.value)}
            testID={`travel-companion-${option.value}`}
          />
        ))}
      </View>

      <Text style={[styles.sectionLabel, styles.secondSectionLabel]}>
        What makes a trip special for you?
      </Text>
      <TextInput
        style={styles.motivationInput}
        placeholder="e.g. trying local food, slow mornings, meeting new people…"
        placeholderTextColor={colors.textMuted}
        value={tripMotivation}
        onChangeText={(text) => setTripMotivation(text.slice(0, MOTIVATION_MAX_LENGTH))}
        multiline
        numberOfLines={4}
        maxLength={MOTIVATION_MAX_LENGTH}
        testID="trip-motivation-input"
      />
      <Text style={styles.charCount}>
        {tripMotivation.length}/{MOTIVATION_MAX_LENGTH}
      </Text>

      {submitState === "error" && submitError && (
        <Text style={styles.errorText} testID="skip-error">
          {submitError}
        </Text>
      )}
    </OnboardingScreenLayout>
  );
}

const styles = StyleSheet.create({
  sectionLabel: { ...typography.subtitle, color: colors.text },
  secondSectionLabel: { marginTop: spacing.md },
  optionGroup: { gap: spacing.sm },
  motivationInput: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.sm + 2,
    color: colors.text,
    minHeight: 96,
    textAlignVertical: "top",
    ...typography.body,
  },
  charCount: {
    ...typography.caption,
    color: colors.textMuted,
    textAlign: "right",
    marginTop: -spacing.xs,
  },
  errorText: { ...typography.body, color: colors.error, marginTop: spacing.sm },
});
