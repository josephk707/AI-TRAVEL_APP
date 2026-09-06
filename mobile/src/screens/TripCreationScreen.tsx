import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { fetchInterests, InterestOption } from "../api/onboarding";
import { ApiError } from "../api/client";
import { createTrip, submitTripNotes } from "../api/trips";
import { Button } from "../components/Button";
import { Screen } from "../components/Screen";
import { ScreenHeader } from "../components/ScreenHeader";
import { SelectableChip } from "../components/SelectableChip";
import { useTranslation } from "../i18n";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { radius, spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";
import { useSafeAreaInsets } from "react-native-safe-area-context";

/** F3/F4 entry point — "destination/dates/budget/interests + 'my own ideas'
 * input" (MOBILE_ARCHITECTURE.md §2 TripCreationScreen). Interests default
 * to onboarding's curated set (F2) so the traveller doesn't re-enter
 * preferences already captured — but can adjust per-trip. */
export function TripCreationScreen(): React.JSX.Element {
  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList, "TripCreation">>();
  const insets = useSafeAreaInsets();
  const { t } = useTranslation();
  const { colors, isDark } = useTheme();
  const styles = useThemedStyles(createStyles);
  const keyboardAppearance = isDark ? "dark" : "light";

  const [title, setTitle] = useState("");
  const [destination, setDestination] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [budget, setBudget] = useState("");
  const [ownIdeas, setOwnIdeas] = useState("");
  const [interests, setInterests] = useState<InterestOption[]>([]);
  const [selectedInterestSlugs, setSelectedInterestSlugs] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchInterests()
      .then(setInterests)
      .catch(() => setInterests([]));
  }, []);

  const toggleInterest = useCallback((slug: string) => {
    setSelectedInterestSlugs((current) =>
      current.includes(slug) ? current.filter((s) => s !== slug) : [...current, slug],
    );
  }, []);

  const canSubmit = title.trim().length > 0 && destination.trim().length > 0 && !submitting;

  const handleSubmit = useCallback(async () => {
    setError(null);
    setSubmitting(true);
    try {
      const trip = await createTrip({
        title: title.trim(),
        destination: destination.trim(),
        start_date: startDate.trim() || undefined,
        end_date: endDate.trim() || undefined,
        budget_planned: budget.trim() ? Number(budget.trim()) : undefined,
      });

      if (ownIdeas.trim()) {
        await submitTripNotes(trip.id, ownIdeas.trim());
      }

      navigation.replace("Chat", {
        tripId: trip.id,
        interests: selectedInterestSlugs,
        useOwnIdeas: ownIdeas.trim().length > 0,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("tripCreation.couldntCreateTrip"));
      setSubmitting(false);
    }
  }, [title, destination, startDate, endDate, budget, ownIdeas, selectedInterestSlugs, navigation, t]);

  return (
    <Screen>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View style={{ paddingTop: insets.top + spacing.sm }}>
          <ScreenHeader title={t("tripCreation.title")} />
        </View>
        <ScrollView contentContainerStyle={styles.container}>
          <Text style={styles.subtitle}>{t("tripCreation.subtitle")}</Text>

          <Text style={styles.label}>{t("tripCreation.tripTitleLabel")}</Text>
          <TextInput
            style={styles.input}
            placeholder="Agra Weekend"
            placeholderTextColor={colors.textFaint}
            keyboardAppearance={keyboardAppearance}
            value={title}
            onChangeText={setTitle}
            testID="trip-title-input"
          />

          <Text style={styles.label}>{t("tripCreation.destinationLabel")}</Text>
          <TextInput
            style={styles.input}
            placeholder="Agra, India"
            placeholderTextColor={colors.textFaint}
            keyboardAppearance={keyboardAppearance}
            value={destination}
            onChangeText={setDestination}
            testID="trip-destination-input"
          />

          <View style={styles.row}>
            <View style={styles.rowItem}>
              <Text style={styles.label}>{t("tripCreation.startDateLabel")}</Text>
              <TextInput
                style={styles.input}
                placeholder="2026-10-10"
                placeholderTextColor={colors.textFaint}
                keyboardAppearance={keyboardAppearance}
                value={startDate}
                onChangeText={setStartDate}
                testID="trip-start-date-input"
              />
            </View>
            <View style={styles.rowItem}>
              <Text style={styles.label}>{t("tripCreation.endDateLabel")}</Text>
              <TextInput
                style={styles.input}
                placeholder="2026-10-13"
                placeholderTextColor={colors.textFaint}
                keyboardAppearance={keyboardAppearance}
                value={endDate}
                onChangeText={setEndDate}
                testID="trip-end-date-input"
              />
            </View>
          </View>

          <Text style={styles.label}>{t("tripCreation.budgetLabel")}</Text>
          <TextInput
            style={styles.input}
            placeholder="15000"
            placeholderTextColor={colors.textFaint}
            keyboardAppearance={keyboardAppearance}
            keyboardType="numeric"
            value={budget}
            onChangeText={setBudget}
            testID="trip-budget-input"
          />

          <Text style={styles.label}>{t("tripCreation.interestsLabel")}</Text>
          <View style={styles.chipGrid}>
            {interests.map((interest) => (
              <SelectableChip
                key={interest.id}
                label={interest.label}
                selected={selectedInterestSlugs.includes(interest.slug)}
                onPress={() => toggleInterest(interest.slug)}
                testID={`interest-chip-${interest.slug}`}
              />
            ))}
          </View>

          <Text style={styles.label}>{t("tripCreation.ownIdeasLabel")}</Text>
          <TextInput
            style={[styles.input, styles.textarea]}
            placeholder={t("tripCreation.ownIdeasPlaceholder")}
            placeholderTextColor={colors.textFaint}
            keyboardAppearance={keyboardAppearance}
            value={ownIdeas}
            onChangeText={setOwnIdeas}
            multiline
            numberOfLines={4}
            testID="trip-own-ideas-input"
          />

          {error && (
            <Text style={styles.errorText} testID="trip-creation-error">
              {error}
            </Text>
          )}

          <View style={styles.submitRow}>
            <Button
              label={submitting ? "" : t("tripCreation.startPlanning")}
              onPress={() => void handleSubmit()}
              disabled={!canSubmit}
              testID="trip-submit-button"
              fullWidth={false}
            />
            {submitting && (
              <ActivityIndicator size="small" color={colors.primaryText} style={styles.spinner} />
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    flex: { flex: 1 },
    container: { padding: spacing.lg, gap: spacing.sm },
    subtitle: { ...typography.body, color: colors.textMuted, marginBottom: spacing.sm },
    label: {
      ...typography.micro,
      color: colors.textMuted,
      textTransform: "uppercase",
      marginTop: spacing.sm,
    },
    input: {
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
      borderRadius: radius.md,
      padding: spacing.sm + 2,
      color: colors.text,
      ...typography.body,
    },
    textarea: { minHeight: 90, textAlignVertical: "top" },
    row: { flexDirection: "row", gap: spacing.sm },
    rowItem: { flex: 1 },
    chipGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
    errorText: { ...typography.body, color: colors.error, marginTop: spacing.sm },
    submitRow: { marginTop: spacing.lg, alignItems: "flex-start" },
    spinner: { position: "absolute", left: spacing.lg, top: spacing.sm + 2 },
  });
