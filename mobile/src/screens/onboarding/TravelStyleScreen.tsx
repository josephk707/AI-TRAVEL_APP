import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback } from "react";
import { StyleSheet, Text, View } from "react-native";

import { OnboardingScreenLayout } from "../../components/OnboardingScreenLayout";
import { SelectableCard } from "../../components/SelectableCard";
import type { OnboardingStackParamList } from "../../navigation/OnboardingNavigator";
import { PACE_OPTIONS, TRAVEL_STYLE_OPTIONS } from "../../onboarding/onboardingOptions";
import { useOnboardingStore } from "../../onboarding/onboardingStore";
import { useSubmitOnboarding } from "../../onboarding/useSubmitOnboarding";
import { spacing, type Theme, typography, useThemedStyles } from "../../theme";

/**
 * Second onboarding screen: travel style + pace.
 *
 * RESOLVED AMBIGUITY (documented, see backend/app/schemas/onboarding.py's
 * matching note): MOBILE_ARCHITECTURE.md's OnboardingStack names exactly
 * one screen for this ("TravelStyleScreen"), while FR-003 requires FOUR
 * distinct inputs (interests, travel style, pace, budget bracket). Rather
 * than adding a screen the architecture doc doesn't name, both closely
 * related "how you like to travel" questions (style + pace) are asked
 * together here, keeping the flow at exactly the 4 documented screens.
 */
export function TravelStyleScreen(): React.JSX.Element {
  const navigation =
    useNavigation<NativeStackNavigationProp<OnboardingStackParamList, "TravelStyle">>();
  const { travelStyle, pace, setTravelStyle, setPace } = useOnboardingStore();
  const { submit, state: submitState, errorMessage: submitError } = useSubmitOnboarding();
  const styles = useThemedStyles(createStyles);

  const handleSkip = useCallback(async () => {
    await submit();
  }, [submit]);

  return (
    <OnboardingScreenLayout
      stepIndex={1}
      title="How do you like to travel?"
      subtitle="Both are optional — pick what feels right, or skip ahead."
      onSkip={handleSkip}
      primaryLabel="Continue"
      onPrimaryPress={() => navigation.navigate("BudgetBracket")}
      primaryBusy={submitState === "submitting"}
      primaryTestID="travel-style-continue-button"
    >
      <Text style={styles.sectionLabel}>Travel style</Text>
      <View style={styles.optionGroup} testID="travel-style-options">
        {TRAVEL_STYLE_OPTIONS.map((option) => (
          <SelectableCard
            key={option.value}
            label={option.label}
            description={option.description}
            icon={option.icon}
            selected={travelStyle === option.value}
            onPress={() => setTravelStyle(option.value)}
            testID={`travel-style-${option.value}`}
          />
        ))}
      </View>

      <Text style={[styles.sectionLabel, styles.secondSectionLabel]}>Pace</Text>
      <View style={styles.optionGroup} testID="pace-options">
        {PACE_OPTIONS.map((option) => (
          <SelectableCard
            key={option.value}
            label={option.label}
            description={option.description}
            icon={option.icon}
            selected={pace === option.value}
            onPress={() => setPace(option.value)}
            testID={`pace-${option.value}`}
          />
        ))}
      </View>

      {submitState === "error" && submitError && (
        <Text style={styles.errorText} testID="skip-error">
          {submitError}
        </Text>
      )}
    </OnboardingScreenLayout>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    sectionLabel: { ...typography.subtitle, color: colors.text },
    secondSectionLabel: { marginTop: spacing.md },
    optionGroup: { gap: spacing.sm },
    errorText: { ...typography.body, color: colors.error, marginTop: spacing.sm },
  });
