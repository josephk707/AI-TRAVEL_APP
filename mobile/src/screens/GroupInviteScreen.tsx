import { Ionicons } from "@expo/vector-icons";
import { useRoute } from "@react-navigation/native";
import type { RouteProp } from "@react-navigation/native";
import { StatusBar } from "expo-status-bar";
import React, { useCallback, useEffect, useState } from "react";
import { Alert, FlatList, Share, StyleSheet, Text, TextInput, View } from "react-native";

import { ApiError } from "../api/client";
import {
  acceptInvite,
  createInvite,
  Invite,
  listTripMembers,
  ReconcileConflict,
  reconcileItinerary,
  submitMemberPreferences,
  TripMember,
} from "../api/group";
import { fetchTrip } from "../api/trips";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LoadingView } from "../components/LoadingView";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { colors, radius, spacing, typography } from "../theme/tokens";

type LoadState =
  | { status: "loading" }
  | { status: "success"; members: TripMember[]; isOrganiser: boolean }
  | { status: "error"; message: string };

/** F19 — Group/Collaborative Trip Planning. Any accepted member can view
 * the shared member list and submit their own preferences; only the
 * organiser can invite others or trigger reconciliation
 * (ARCHITECTURE_REVIEW.md H5's resolved reading — see
 * app/services/group_service.py's module docstring). */
export function GroupInviteScreen(): React.JSX.Element {
  const route = useRoute<RouteProp<RootStackParamList, "GroupInvite">>();
  const { tripId } = route.params;
  const { user } = useAuth();

  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [invite, setInvite] = useState<Invite | null>(null);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [inviteTokenInput, setInviteTokenInput] = useState("");
  const [acceptError, setAcceptError] = useState<string | null>(null);
  const [interestsText, setInterestsText] = useState("");
  const [budgetMaxText, setBudgetMaxText] = useState("");
  const [prefsError, setPrefsError] = useState<string | null>(null);
  const [prefsSaved, setPrefsSaved] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [reconcileError, setReconcileError] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<ReconcileConflict[]>([]);

  const resolveMembers = useCallback(async (): Promise<LoadState> => {
    try {
      const [members, trip] = await Promise.all([listTripMembers(tripId), fetchTrip(tripId)]);
      return { status: "success", members, isOrganiser: trip.owner_id === user?.id };
    } catch (error) {
      return {
        status: "error",
        message: error instanceof ApiError ? error.message : "Couldn't load trip members.",
      };
    }
  }, [tripId, user]);

  useEffect(() => {
    let cancelled = false;
    resolveMembers().then((result) => {
      if (!cancelled) setState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [resolveMembers]);

  const load = useCallback(() => {
    setState({ status: "loading" });
    void resolveMembers().then(setState);
  }, [resolveMembers]);

  const handleCreateInvite = useCallback(async () => {
    setInviteError(null);
    try {
      const result = await createInvite(tripId, "link");
      setInvite(result);
      void Share.share({ message: `Join my trip on Yatra AI: ${result.invite_url}` });
    } catch (error) {
      setInviteError(error instanceof ApiError ? error.message : "Couldn't create an invite.");
    }
  }, [tripId]);

  const handleAcceptInvite = useCallback(async () => {
    if (!inviteTokenInput.trim()) return;
    setAcceptError(null);
    try {
      await acceptInvite(inviteTokenInput.trim());
      setInviteTokenInput("");
      Alert.alert("Joined!", "You've been added to this trip.");
      load();
    } catch (error) {
      setAcceptError(error instanceof ApiError ? error.message : "Couldn't accept that invite.");
    }
  }, [inviteTokenInput, load]);

  const handleSavePreferences = useCallback(async () => {
    if (!user) return;
    setPrefsError(null);
    setPrefsSaved(false);
    try {
      const interests = interestsText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const budgetMax = budgetMaxText.trim() ? Number(budgetMaxText) : undefined;
      await submitMemberPreferences(tripId, user.id, interests, budgetMax);
      setPrefsSaved(true);
    } catch (error) {
      setPrefsError(
        error instanceof ApiError ? error.message : "Couldn't save your preferences.",
      );
    }
  }, [tripId, user, interestsText, budgetMaxText]);

  const handleReconcile = useCallback(async () => {
    setReconciling(true);
    setReconcileError(null);
    try {
      const result = await reconcileItinerary(tripId);
      setConflicts(result.conflicts);
      Alert.alert("Plan reconciled", result.summary);
    } catch (error) {
      setReconcileError(
        error instanceof ApiError ? error.message : "Couldn't reconcile the group's plan.",
      );
    } finally {
      setReconciling(false);
    }
  }, [tripId]);

  return (
    <View style={styles.flex}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <Text style={styles.title}>Group trip</Text>
      </View>

      {state.status === "loading" && (
        <View style={styles.centered}>
          <LoadingView label="Loading group details…" />
        </View>
      )}

      {state.status === "error" && (
        <View style={styles.centered} testID="group-error">
          <Text style={styles.errorText}>{state.message}</Text>
          <Button label="Retry" onPress={load} testID="group-retry-button" />
        </View>
      )}

      {state.status === "success" && (
        <FlatList
          testID="group-content"
          data={state.members}
          keyExtractor={(m) => m.user_id}
          contentContainerStyle={styles.list}
          ListHeaderComponent={
            <View style={styles.section}>
              {state.isOrganiser && (
                <Card style={styles.card}>
                  <Text style={styles.cardTitle}>Invite someone</Text>
                  <Button label="Create invite link" onPress={() => void handleCreateInvite()} testID="create-invite-button" />
                  {invite && (
                    <Text style={styles.inviteToken} testID="invite-token-display">
                      {invite.token}
                    </Text>
                  )}
                  {inviteError && <Text style={styles.errorText}>{inviteError}</Text>}
                </Card>
              )}

              <Card style={styles.card}>
                <Text style={styles.cardTitle}>Have an invite code?</Text>
                <TextInput
                  style={styles.input}
                  placeholder="Paste invite code"
                  placeholderTextColor={colors.textMuted}
                  value={inviteTokenInput}
                  onChangeText={setInviteTokenInput}
                  testID="invite-token-input"
                />
                <Button label="Join trip" onPress={() => void handleAcceptInvite()} testID="accept-invite-button" />
                {acceptError && <Text style={styles.errorText}>{acceptError}</Text>}
              </Card>

              <Card style={styles.card}>
                <Text style={styles.cardTitle}>Your preferences</Text>
                <TextInput
                  style={styles.input}
                  placeholder="Interests (comma separated)"
                  placeholderTextColor={colors.textMuted}
                  value={interestsText}
                  onChangeText={setInterestsText}
                  testID="preferences-interests-input"
                />
                <TextInput
                  style={styles.input}
                  placeholder="Your max budget (optional)"
                  placeholderTextColor={colors.textMuted}
                  keyboardType="numeric"
                  value={budgetMaxText}
                  onChangeText={setBudgetMaxText}
                  testID="preferences-budget-input"
                />
                <Button
                  label="Save my preferences"
                  onPress={() => void handleSavePreferences()}
                  testID="save-preferences-button"
                />
                {prefsSaved && <Text style={styles.successText}>Saved!</Text>}
                {prefsError && <Text style={styles.errorText}>{prefsError}</Text>}
              </Card>

              {state.isOrganiser && (
                <Card style={styles.card}>
                  <Text style={styles.cardTitle}>Reconcile the group&apos;s plan</Text>
                  <Text style={styles.cardHint}>
                    Merges every submitted member&apos;s preferences into one plan and explains
                    any trade-offs.
                  </Text>
                  <Button
                    label={reconciling ? "Reconciling…" : "Reconcile now"}
                    onPress={() => void handleReconcile()}
                    disabled={reconciling}
                    testID="reconcile-button"
                  />
                  {reconcileError && <Text style={styles.errorText}>{reconcileError}</Text>}
                  {conflicts.map((c, i) => (
                    <View key={i} style={styles.conflictRow} testID={`conflict-${i}`}>
                      <Text style={styles.conflictDescription}>{c.description}</Text>
                      <Text style={styles.conflictResolution}>{c.resolution}</Text>
                    </View>
                  ))}
                </Card>
              )}

              <Text style={styles.membersHeading}>Members ({state.members.length})</Text>
            </View>
          }
          renderItem={({ item }) => (
            <View style={styles.memberRow} testID={`member-${item.user_id}`}>
              <Ionicons
                name={item.role === "organiser" ? "star" : "person-outline"}
                size={18}
                color={colors.primary}
              />
              <Text style={styles.memberText}>{item.display_name ?? "Traveller"}</Text>
              <Text style={styles.memberStatus}>{item.invite_status}</Text>
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
  errorText: { ...typography.body, color: colors.error },
  successText: { ...typography.caption, color: colors.success },
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.sm },
  section: { gap: spacing.sm },
  card: { gap: spacing.sm, marginTop: spacing.sm },
  cardTitle: { ...typography.subtitle, color: colors.text },
  cardHint: { ...typography.caption, color: colors.textMuted },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.sm + 2,
    color: colors.text,
    ...typography.body,
  },
  inviteToken: {
    ...typography.caption,
    color: colors.primary,
    backgroundColor: colors.surface,
    padding: spacing.sm,
    borderRadius: radius.sm,
  },
  conflictRow: {
    backgroundColor: colors.surface,
    borderRadius: radius.sm,
    padding: spacing.sm,
    gap: 2,
  },
  conflictDescription: { ...typography.body, color: colors.text },
  conflictResolution: { ...typography.caption, color: colors.textMuted },
  membersHeading: { ...typography.subtitle, color: colors.text, marginTop: spacing.md },
  memberRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.xs,
  },
  memberText: { ...typography.body, color: colors.text, flex: 1 },
  memberStatus: { ...typography.caption, color: colors.textMuted, textTransform: "capitalize" },
});
