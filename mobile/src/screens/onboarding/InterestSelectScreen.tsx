import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback, useEffect, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { fetchInterests, InterestOption } from "../../api/onboarding";
import { ApiError } from "../../api/client";
import { Button } from "../../components/Button";
import { LoadingView } from "../../components/LoadingView";
import { OnboardingScreenLayout } from "../../components/OnboardingScreenLayout";
import { SelectableChip } from "../../components/SelectableChip";
import type { OnboardingStackParamList } from "../../navigation/OnboardingNavigator";
import { useOnboardingStore } from "../../onboarding/onboardingStore";
import { useSubmitOnboarding } from "../../onboarding/useSubmitOnboarding";
import { spacing, type Theme, typography, useThemedStyles } from "../../theme";

type LoadState =
  | { status: "loading" }
  | { status: "success"; interests: InterestOption[] }
  | { status: "error"; message: string };

/** First onboarding screen: multi-select interest tags (FR-003's "interest
 * themes"). Nothing is required — 0 selections is a valid, supported
 * choice (the user can still proceed or Skip entirely). */
export function InterestSelectScreen(): React.JSX.Element {
  const navigation =
    useNavigation<NativeStackNavigationProp<OnboardingStackParamList, "InterestSelect">>();
  const { interestIds, toggleInterest } = useOnboardingStore();
  const { submit, state: submitState, errorMessage: submitError } = useSubmitOnboarding();
  const styles = useThemedStyles(createStyles);
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });

  // Resolves the next LoadState without setting state itself, so the
  // effect below can set state only inside a .then() callback
  // (react-hooks/set-state-in-effect) while the retry button — a real
  // event handler, not an effect — is free to set the "loading" state
  // synchronously before calling this.
  const resolveInterests = useCallback(async (): Promise<LoadState> => {
    try {
      const interests = await fetchInterests();
      return { status: "success", interests };
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "Couldn't load interests right now.";
      return { status: "error", message };
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    resolveInterests().then((result) => {
      if (!cancelled) setLoadState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [resolveInterests]);

  const loadInterests = useCallback(() => {
    setLoadState({ status: "loading" });
    void resolveInterests().then(setLoadState);
  }, [resolveInterests]);

  const handleSkip = useCallback(async () => {
    await submit();
  }, [submit]);

  return (
    <OnboardingScreenLayout
      stepIndex={0}
      title="What excites you?"
      subtitle="Pick as many as you like — this helps us shape your first itinerary."
      onSkip={handleSkip}
      primaryLabel="Continue"
      onPrimaryPress={() => navigation.navigate("TravelStyle")}
      primaryBusy={submitState === "submitting"}
      primaryTestID="interest-continue-button"
    >
      {loadState.status === "loading" && <LoadingView label="Loading interests…" />}

      {loadState.status === "error" && (
        <View testID="interests-error">
          <Text style={styles.errorText}>{loadState.message}</Text>
          <View style={styles.retryButton}>
            <Button label="Retry" onPress={loadInterests} testID="interests-retry-button" />
          </View>
        </View>
      )}

      {loadState.status === "success" && (
        <View style={styles.chipGrid} testID="interests-grid">
          {loadState.interests.map((interest) => (
            <SelectableChip
              key={interest.id}
              label={interest.label}
              selected={interestIds.includes(interest.id)}
              onPress={() => toggleInterest(interest.id)}
              testID={`interest-chip-${interest.slug}`}
            />
          ))}
        </View>
      )}

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
    chipGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
    errorText: { ...typography.body, color: colors.error, marginTop: spacing.sm },
    retryButton: { marginTop: spacing.md, alignSelf: "flex-start" },
  });
