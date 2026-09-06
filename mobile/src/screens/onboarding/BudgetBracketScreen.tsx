import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback } from "react";
import { StyleSheet, Text, View } from "react-native";

import { OnboardingScreenLayout } from "../../components/OnboardingScreenLayout";
import { SelectableCard } from "../../components/SelectableCard";
import type { OnboardingStackParamList } from "../../navigation/OnboardingNavigator";
import { BUDGET_BRACKET_OPTIONS } from "../../onboarding/onboardingOptions";
import { useOnboardingStore } from "../../onboarding/onboardingStore";
import { useSubmitOnboarding } from "../../onboarding/useSubmitOnboarding";
import { spacing, type Theme, typography, useThemedStyles } from "../../theme";

export function BudgetBracketScreen(): React.JSX.Element {
  const navigation =
    useNavigation<NativeStackNavigationProp<OnboardingStackParamList, "BudgetBracket">>();
  const { budgetBracket, setBudgetBracket } = useOnboardingStore();
  const { submit, state: submitState, errorMessage: submitError } = useSubmitOnboarding();
  const styles = useThemedStyles(createStyles);

  const handleSkip = useCallback(async () => {
    await submit();
  }, [submit]);

  return (
    <OnboardingScreenLayout
      stepIndex={2}
      title="What's your budget style?"
      subtitle="A rough idea helps us suggest the right places — you can change this anytime."
      onSkip={handleSkip}
      primaryLabel="Continue"
      onPrimaryPress={() => navigation.navigate("TravelMotivation")}
      primaryBusy={submitState === "submitting"}
      primaryTestID="budget-continue-button"
    >
      <View style={styles.optionGroup} testID="budget-bracket-options">
        {BUDGET_BRACKET_OPTIONS.map((option) => (
          <SelectableCard
            key={option.value}
            label={option.label}
            description={option.description}
            icon={option.icon}
            selected={budgetBracket === option.value}
            onPress={() => setBudgetBracket(option.value)}
            testID={`budget-bracket-${option.value}`}
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
    optionGroup: { gap: spacing.sm },
    errorText: { ...typography.body, color: colors.error, marginTop: spacing.sm },
  });
