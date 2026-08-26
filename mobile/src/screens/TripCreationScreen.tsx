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
import { StatusBar } from "expo-status-bar";

import { fetchInterests, InterestOption } from "../api/onboarding";
import { ApiError } from "../api/client";
import { createTrip, submitTripNotes } from "../api/trips";
import { Button } from "../components/Button";
import { SelectableChip } from "../components/SelectableChip";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { colors, radius, spacing, typography } from "../theme/tokens";

/** F3/F4 entry point — "destination/dates/budget/interests + 'my own ideas'
 * input" (MOBILE_ARCHITECTURE.md §2 TripCreationScreen). Interests default
 * to onboarding's curated set (F2) so the traveller doesn't re-enter
 * preferences already captured — but can adjust per-trip. */
export function TripCreationScreen(): React.JSX.Element {
  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList, "TripCreation">>();

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
      setError(err instanceof ApiError ? err.message : "Couldn't create this trip.");
      setSubmitting(false);
    }
  }, [title, destination, startDate, endDate, budget, ownIdeas, selectedInterestSlugs, navigation]);

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>Plan a new trip</Text>
        <Text style={styles.subtitle}>
          Tell Yatra AI where you are headed — it will build a personalised itinerary.
        </Text>

        <Text style={styles.label}>Trip title</Text>
        <TextInput
          style={styles.input}
          placeholder="Agra Weekend"
          placeholderTextColor={colors.textMuted}
          value={title}
          onChangeText={setTitle}
          testID="trip-title-input"
        />

        <Text style={styles.label}>Destination</Text>
        <TextInput
          style={styles.input}
          placeholder="Agra, India"
          placeholderTextColor={colors.textMuted}
          value={destination}
          onChangeText={setDestination}
          testID="trip-destination-input"
        />

        <View style={styles.row}>
          <View style={styles.rowItem}>
            <Text style={styles.label}>Start date</Text>
            <TextInput
              style={styles.input}
              placeholder="2026-10-10"
              placeholderTextColor={colors.textMuted}
              value={startDate}
              onChangeText={setStartDate}
              testID="trip-start-date-input"
            />
          </View>
          <View style={styles.rowItem}>
            <Text style={styles.label}>End date</Text>
            <TextInput
              style={styles.input}
              placeholder="2026-10-13"
              placeholderTextColor={colors.textMuted}
              value={endDate}
              onChangeText={setEndDate}
              testID="trip-end-date-input"
            />
          </View>
        </View>

        <Text style={styles.label}>Budget (INR)</Text>
        <TextInput
          style={styles.input}
          placeholder="15000"
          placeholderTextColor={colors.textMuted}
          keyboardType="numeric"
          value={budget}
          onChangeText={setBudget}
          testID="trip-budget-input"
        />

        <Text style={styles.label}>Interests for this trip</Text>
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

        <Text style={styles.label}>Your own ideas (optional)</Text>
        <TextInput
          style={[styles.input, styles.textarea]}
          placeholder="e.g. I really want to see the Taj Mahal at sunrise, and try local street food…"
          placeholderTextColor={colors.textMuted}
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
            label={submitting ? "" : "Start planning"}
            onPress={() => void handleSubmit()}
            disabled={!canSubmit}
            testID="trip-submit-button"
          />
          {submitting && (
            <ActivityIndicator size="small" color={colors.primaryText} style={styles.spinner} />
          )}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  container: { padding: spacing.lg, gap: spacing.sm },
  title: { ...typography.title, color: colors.text },
  subtitle: { ...typography.body, color: colors.textMuted, marginBottom: spacing.sm },
  label: { ...typography.caption, color: colors.textMuted, marginTop: spacing.sm },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
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
