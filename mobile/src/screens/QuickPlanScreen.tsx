import { Ionicons } from "@expo/vector-icons";
import * as Location from "expo-location";
import { StatusBar } from "expo-status-bar";
import React, { useCallback, useState } from "react";
import { ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { ApiError } from "../api/client";
import { createQuickPlan, QuickPlan, saveQuickPlanToCollection } from "../api/quickPlans";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { GradientBackground } from "../components/GradientBackground";
import { colors, radius, spacing, typography } from "../theme/tokens";

type ResultState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; plan: QuickPlan }
  | { status: "error"; message: string };

/** F22 — Weekend/Local Outing Quick Plan. Deliberately separate from
 * "Plan a trip" (§25.1) — a short, scoped-down outing, not a multi-day
 * itinerary; FR-015's own business rule (states plainly when local data
 * is insufficient, never returns a low-quality generic list). */
export function QuickPlanScreen(): React.JSX.Element {
  const [timeText, setTimeText] = useState("120");
  const [budgetText, setBudgetText] = useState("");
  const [occasion, setOccasion] = useState("");
  const [locationError, setLocationError] = useState<string | null>(null);
  const [result, setResult] = useState<ResultState>({ status: "idle" });
  const [saveResult, setSaveResult] = useState<string | null>(null);

  const generate = useCallback(async () => {
    const timeAvailableMin = Number(timeText);
    if (!Number.isFinite(timeAvailableMin) || timeAvailableMin < 15) {
      setResult({ status: "error", message: "Enter a valid amount of time (at least 15 minutes)." });
      return;
    }

    setResult({ status: "loading" });
    setSaveResult(null);
    setLocationError(null);

    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      let lat: number | undefined;
      let lng: number | undefined;
      if (permission.granted) {
        const position = await Location.getCurrentPositionAsync({});
        lat = position.coords.latitude;
        lng = position.coords.longitude;
      } else {
        setLocationError("Location access denied — using your home region instead, if set.");
      }

      const plan = await createQuickPlan(timeAvailableMin, {
        budget: budgetText.trim() ? Number(budgetText) : undefined,
        occasion: occasion.trim() || undefined,
        lat,
        lng,
      });
      setResult({ status: "success", plan });
    } catch (error) {
      setResult({
        status: "error",
        message: error instanceof ApiError ? error.message : "Couldn't build a quick plan.",
      });
    }
  }, [timeText, budgetText, occasion]);

  const saveToCollection = useCallback(async () => {
    if (result.status !== "success") return;
    try {
      const saved = await saveQuickPlanToCollection(result.plan.id);
      setSaveResult(`Saved to "${saved.collection_name}"`);
    } catch (error) {
      setSaveResult(
        error instanceof ApiError ? error.message : "Couldn't save this plan to a collection.",
      );
    }
  }, [result]);

  return (
    <GradientBackground>
      <ScrollView style={styles.flex} contentContainerStyle={styles.content}>
      <StatusBar style="light" />
      <Text style={styles.title}>Quick plan</Text>
      <Text style={styles.subtitle}>A short local outing, planned in seconds.</Text>

      <Card style={styles.form}>
        <Text style={styles.label}>Time available (minutes)</Text>
        <TextInput
          style={styles.input}
          keyboardType="numeric"
          value={timeText}
          onChangeText={setTimeText}
          testID="quick-plan-time-input"
        />
        <Text style={styles.label}>Budget (optional)</Text>
        <TextInput
          style={styles.input}
          placeholder="₹"
          placeholderTextColor={colors.textMuted}
          keyboardType="numeric"
          value={budgetText}
          onChangeText={setBudgetText}
          testID="quick-plan-budget-input"
        />
        <Text style={styles.label}>Occasion</Text>
        <TextInput
          style={styles.input}
          placeholder="e.g. casual, date, with friends"
          placeholderTextColor={colors.textMuted}
          value={occasion}
          onChangeText={setOccasion}
          testID="quick-plan-occasion-input"
        />
        {locationError && <Text style={styles.hintText}>{locationError}</Text>}
        <Button
          label={result.status === "loading" ? "Building…" : "Build my plan"}
          onPress={() => void generate()}
          disabled={result.status === "loading"}
          testID="generate-quick-plan-button"
        />
      </Card>

      {result.status === "error" && (
        <Text style={styles.errorText} testID="quick-plan-error">
          {result.message}
        </Text>
      )}

      {result.status === "success" && (
        <Card style={styles.resultCard} testID="quick-plan-result">
          <Text style={styles.resultSummary}>{result.plan.summary}</Text>
          {result.plan.items.map((item) => (
            <View key={item.poi_id} style={styles.itemRow} testID={`quick-plan-item-${item.poi_id}`}>
              <Ionicons name="location-outline" size={18} color={colors.primary} />
              <Text style={styles.itemText}>{item.poi_name}</Text>
            </View>
          ))}
          <Button
            label="Save to a collection"
            onPress={() => void saveToCollection()}
            testID="save-quick-plan-button"
          />
          {saveResult && <Text style={styles.hintText}>{saveResult}</Text>}
        </Card>
      )}
      </ScrollView>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.md },
  title: { ...typography.title, color: colors.text },
  subtitle: { ...typography.body, color: colors.textMuted, marginBottom: spacing.sm },
  form: { gap: spacing.sm },
  label: { ...typography.caption, color: colors.textMuted },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    padding: spacing.sm + 2,
    color: colors.text,
    ...typography.body,
  },
  hintText: { ...typography.caption, color: colors.textMuted },
  errorText: { ...typography.body, color: colors.error, textAlign: "center" },
  resultCard: { gap: spacing.sm },
  resultSummary: { ...typography.body, color: colors.text },
  itemRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  itemText: { ...typography.body, color: colors.text },
});
