import { useRoute } from "@react-navigation/native";
import type { RouteProp } from "@react-navigation/native";
import { Ionicons } from "@expo/vector-icons";
import { StatusBar } from "expo-status-bar";
import React, { useCallback, useEffect, useState } from "react";
import { FlatList, Switch, StyleSheet, Text, TextInput, View } from "react-native";

import { ApiError } from "../api/client";
import { BudgetSummary, Expense, ExpenseCategory, fetchBudgetSummary, logExpense } from "../api/budget";
import { listTripMembers, TripMember } from "../api/group";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LoadingView } from "../components/LoadingView";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { colors, radius, spacing, typography } from "../theme/tokens";

type LoadState =
  | { status: "loading" }
  | { status: "success"; summary: BudgetSummary }
  | { status: "error"; message: string };

const CATEGORIES: ExpenseCategory[] = ["lodging", "food", "transport", "activity", "other"];

/** F15 — Budget Estimate. Over-budget is always advisory (BR-016) — this
 * screen surfaces it visibly (a banner, never a block) rather than
 * disabling expense logging. */
export function BudgetViewScreen(): React.JSX.Element {
  const route = useRoute<RouteProp<RootStackParamList, "BudgetView">>();
  const { tripId } = route.params;
  const { user } = useAuth();

  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [category, setCategory] = useState<ExpenseCategory>("food");
  const [amountText, setAmountText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [overBudgetNotice, setOverBudgetNotice] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [members, setMembers] = useState<TripMember[]>([]);
  const [splitEqually, setSplitEqually] = useState(false);

  useEffect(() => {
    listTripMembers(tripId)
      .then(setMembers)
      .catch(() => undefined);
  }, [tripId]);

  const resolveBudget = useCallback(async (): Promise<LoadState> => {
    try {
      const summary = await fetchBudgetSummary(tripId);
      return { status: "success", summary };
    } catch (error) {
      return {
        status: "error",
        message: error instanceof ApiError ? error.message : "Couldn't load your budget.",
      };
    }
  }, [tripId]);

  useEffect(() => {
    let cancelled = false;
    resolveBudget().then((result) => {
      if (!cancelled) setState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [resolveBudget]);

  const load = useCallback(() => {
    setState({ status: "loading" });
    void resolveBudget().then(setState);
  }, [resolveBudget]);

  const submit = useCallback(async () => {
    const amount = Number(amountText);
    if (!Number.isFinite(amount) || amount <= 0) {
      setSubmitError("Enter a valid amount.");
      return;
    }
    setSubmitError(null);
    setSubmitting(true);
    try {
      const splitWith =
        splitEqually && members.length > 0 && user
          ? (() => {
              const participantIds = [user.id, ...members.map((m) => m.user_id)];
              const share = 1 / participantIds.length;
              return participantIds.map((userId) => ({ user_id: userId, share }));
            })()
          : undefined;
      const { overBudget } = await logExpense(tripId, category, amount, "INR", splitWith);
      setOverBudgetNotice(overBudget);
      setAmountText("");
      load();
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error.message : "Couldn't log that expense.");
    } finally {
      setSubmitting(false);
    }
  }, [tripId, category, amountText, load, splitEqually, members, user]);

  return (
    <View style={styles.flex}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <Text style={styles.title}>Trip budget</Text>
      </View>

      {state.status === "loading" && (
        <View style={styles.centered}>
          <LoadingView label="Loading your budget…" />
        </View>
      )}

      {state.status === "error" && (
        <View style={styles.centered} testID="budget-error">
          <Text style={styles.errorText}>{state.message}</Text>
          <Button label="Retry" onPress={load} testID="budget-retry-button" />
        </View>
      )}

      {state.status === "success" && (
        <FlatList
          testID="budget-content"
          data={state.summary.expenses}
          keyExtractor={(expense) => expense.id}
          contentContainerStyle={styles.list}
          ListHeaderComponent={
            <View style={styles.summarySection}>
              <Card style={styles.summaryCard}>
                <Text style={styles.summaryLabel}>Planned budget</Text>
                <Text style={styles.summaryValue}>
                  {state.summary.planned_budget != null ? `₹${state.summary.planned_budget}` : "Not set"}
                </Text>
                <Text style={styles.summaryLabel}>Spent so far</Text>
                <Text style={styles.summaryValue}>₹{state.summary.total_spent}</Text>
                {state.summary.over_budget && (
                  <View style={styles.overBudgetBanner} testID="budget-over-banner">
                    <Ionicons name="alert-circle-outline" size={18} color={colors.warning} />
                    <Text style={styles.overBudgetText}>
                      You&apos;re over your planned budget — this is just a heads-up, nothing is blocked.
                    </Text>
                  </View>
                )}
                {Object.keys(state.summary.per_member_owed).length > 0 && (
                  <View style={styles.owedSection} testID="per-member-owed">
                    <Text style={styles.summaryLabel}>Who owes what</Text>
                    {Object.entries(state.summary.per_member_owed).map(([userId, amount]) => (
                      <Text key={userId} style={styles.owedRow}>
                        {userId === user?.id ? "You" : userId.slice(0, 8)}: ₹{amount}
                      </Text>
                    ))}
                  </View>
                )}
              </Card>

              <Card style={styles.form}>
                <Text style={styles.formTitle}>Log an expense</Text>
                <View style={styles.categoryRow}>
                  {CATEGORIES.map((cat) => (
                    <Text
                      key={cat}
                      onPress={() => setCategory(cat)}
                      testID={`budget-category-${cat}`}
                      style={[styles.categoryChip, category === cat && styles.categoryChipActive]}
                    >
                      {cat}
                    </Text>
                  ))}
                </View>
                <TextInput
                  style={styles.amountInput}
                  placeholder="Amount (₹)"
                  placeholderTextColor={colors.textMuted}
                  keyboardType="numeric"
                  value={amountText}
                  onChangeText={setAmountText}
                  testID="budget-amount-input"
                />
                {members.length > 0 && (
                  <View style={styles.splitRow} testID="split-equally-row">
                    <Text style={styles.formTitle}>Split equally with the group</Text>
                    <Switch
                      value={splitEqually}
                      onValueChange={setSplitEqually}
                      testID="split-equally-switch"
                    />
                  </View>
                )}
                {submitError && <Text style={styles.errorText}>{submitError}</Text>}
                {overBudgetNotice && (
                  <Text style={styles.overBudgetInlineText} testID="budget-over-toast">
                    Logged — heads up, this puts you over your planned budget.
                  </Text>
                )}
                <Button
                  label={submitting ? "Saving…" : "Log expense"}
                  onPress={() => void submit()}
                  disabled={submitting}
                  testID="budget-log-expense-button"
                />
              </Card>

              <Text style={styles.expensesHeading}>Expenses</Text>
            </View>
          }
          ListEmptyComponent={
            <Text style={styles.emptyText} testID="budget-expenses-empty">
              No expenses logged yet.
            </Text>
          }
          renderItem={({ item }: { item: Expense }) => (
            <View style={styles.expenseRow} testID={`expense-${item.id}`}>
              <Text style={styles.expenseCategory}>{item.category}</Text>
              <Text style={styles.expenseAmount}>
                {item.currency} {item.amount}
              </Text>
            </View>
          )}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  header: { padding: spacing.lg, paddingBottom: spacing.sm },
  title: { ...typography.title, color: colors.text },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
  errorText: { ...typography.body, color: colors.error, textAlign: "center" },
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.sm },
  summarySection: { gap: spacing.md, marginBottom: spacing.sm },
  summaryCard: { gap: spacing.xs },
  summaryLabel: { ...typography.caption, color: colors.textMuted, marginTop: spacing.xs },
  summaryValue: { ...typography.subtitle, color: colors.text },
  overBudgetBanner: {
    flexDirection: "row",
    gap: spacing.xs,
    alignItems: "flex-start",
    backgroundColor: "#FDF3D8",
    borderRadius: radius.sm,
    padding: spacing.sm,
    marginTop: spacing.sm,
  },
  overBudgetText: { ...typography.caption, color: colors.warning, flex: 1 },
  overBudgetInlineText: { ...typography.caption, color: colors.warning },
  owedSection: { marginTop: spacing.sm, gap: 2 },
  owedRow: { ...typography.caption, color: colors.text },
  splitRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  form: { gap: spacing.sm },
  formTitle: { ...typography.subtitle, color: colors.text },
  categoryRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  categoryChip: {
    ...typography.caption,
    color: colors.text,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm,
    textTransform: "capitalize",
  },
  categoryChipActive: { backgroundColor: colors.primary, color: colors.primaryText, borderColor: colors.primary },
  amountInput: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    backgroundColor: colors.background,
    borderRadius: radius.md,
    padding: spacing.sm + 2,
    color: colors.text,
    ...typography.body,
  },
  expensesHeading: { ...typography.subtitle, color: colors.text, marginTop: spacing.sm },
  emptyText: { ...typography.body, color: colors.textMuted },
  expenseRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.md,
  },
  expenseCategory: { ...typography.body, color: colors.text, textTransform: "capitalize" },
  expenseAmount: { ...typography.body, color: colors.text },
});
