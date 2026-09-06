import { useNavigation, useRoute } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import type { RouteProp } from "@react-navigation/native";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { StatusBar } from "expo-status-bar";

import { ApiError } from "../api/client";
import {
  fetchTrip,
  generateItinerary,
  modifyItinerary,
  updateTrip,
  type GenerateItineraryResult,
} from "../api/trips";
import { ChatBubble } from "../components/ChatBubble";
import { GradientBackground } from "../components/GradientBackground";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { colors, radius, spacing, typography } from "../theme/tokens";

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
}

let messageCounter = 0;
function nextId(): string {
  messageCounter += 1;
  return `msg-${messageCounter}`;
}

/** F3 (initial generation) + F5 (conversational modification) — the
 * "conversational planner, primary interaction surface" (MOBILE_ARCHITECTURE.md
 * §2/§25). Generation runs automatically on first entry; every message
 * after that is a scoped modification request. */
export function ChatScreen(): React.JSX.Element {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList, "Chat">>();
  const route = useRoute<RouteProp<RootStackParamList, "Chat">>();
  const { tripId, interests, useOwnIdeas } = route.params;

  const [messages, setMessages] = useState<Message[]>([]);
  const [generating, setGenerating] = useState(true);
  const [sending, setSending] = useState(false);
  const [draft, setDraft] = useState("");
  const [missingFields, setMissingFields] = useState<string[] | null>(null);
  const [clarifyBudget, setClarifyBudget] = useState("");
  const [clarifyStart, setClarifyStart] = useState("");
  const [clarifyEnd, setClarifyEnd] = useState("");
  const [hasItinerary, setHasItinerary] = useState(false);
  const listRef = useRef<FlatList<Message>>(null);

  const appendAssistant = useCallback((text: string) => {
    setMessages((current) => [...current, { id: nextId(), role: "assistant", text }]);
  }, []);

  const summarize = useCallback((result: GenerateItineraryResult) => {
    let text = result.summary;
    if (result.degraded) {
      text += " (Live planning was temporarily unavailable, so this is a curated starter plan.)";
    }
    if (result.budget_summary?.over_budget) {
      text += ` Heads up — the estimated total is a bit over your stated budget.`;
    }
    if (result.conflicts.length > 0) {
      text += ` A couple of notes: ${result.conflicts.join(" ")}`;
    }
    return text;
  }, []);

  const runGeneration = useCallback(
    async (overrides?: { budget?: number; start_date?: string; end_date?: string }) => {
      setGenerating(true);
      setMissingFields(null);
      try {
        if (overrides && (overrides.budget || overrides.start_date || overrides.end_date)) {
          await updateTrip(tripId, {
            budget_planned: overrides.budget,
            start_date: overrides.start_date,
            end_date: overrides.end_date,
          });
        }
        const result = await generateItinerary(tripId, {
          interests,
          use_own_ideas: useOwnIdeas,
          budget: overrides?.budget,
          time_window:
            overrides?.start_date && overrides?.end_date
              ? { start: overrides.start_date, end: overrides.end_date }
              : undefined,
        });
        setHasItinerary(true);
        appendAssistant(summarize(result));
      } catch (err) {
        if (err instanceof ApiError && err.code === "CLARIFICATION_NEEDED") {
          appendAssistant(err.message);
          const fields = (err.details as { missing_fields?: string[] } | undefined)
            ?.missing_fields ?? ["destination", "budget", "dates"];
          setMissingFields(fields);
        } else {
          appendAssistant(
            err instanceof ApiError
              ? `I ran into a problem: ${err.message}`
              : "Something went wrong while planning your trip.",
          );
        }
      } finally {
        setGenerating(false);
      }
    },
    [tripId, interests, useOwnIdeas, appendAssistant, summarize],
  );

  useEffect(() => {
    let cancelled = false;
    fetchTrip(tripId)
      .then((trip) => {
        if (cancelled) return;
        if (trip.generation_status === "none") {
          appendAssistant(`Planning your trip to ${trip.destination}…`);
          void runGeneration();
        } else {
          setGenerating(false);
          setHasItinerary(true);
          appendAssistant("Welcome back! Ask me for any changes to your plan.");
        }
      })
      .catch(() => {
        if (!cancelled) setGenerating(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tripId]);

  const handleClarifySubmit = useCallback(() => {
    void runGeneration({
      budget: clarifyBudget.trim() ? Number(clarifyBudget.trim()) : undefined,
      start_date: clarifyStart.trim() || undefined,
      end_date: clarifyEnd.trim() || undefined,
    });
  }, [runGeneration, clarifyBudget, clarifyStart, clarifyEnd]);

  const handleSend = useCallback(async () => {
    const text = draft.trim();
    if (!text || sending) return;
    setMessages((current) => [...current, { id: nextId(), role: "user", text }]);
    setDraft("");
    setSending(true);
    try {
      const result = await modifyItinerary(tripId, text);
      appendAssistant(result.reply);
    } catch (err) {
      appendAssistant(
        err instanceof ApiError
          ? `I couldn't apply that: ${err.message}`
          : "Something went wrong applying that change.",
      );
    } finally {
      setSending(false);
    }
  }, [draft, sending, tripId, appendAssistant]);

  useEffect(() => {
    listRef.current?.scrollToEnd({ animated: true });
  }, [messages]);

  return (
    <GradientBackground>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={80}
      >
      <StatusBar style="light" />
      <View style={styles.header}>
        <Text style={styles.title}>Trip planner</Text>
        {hasItinerary && (
          <Pressable
            onPress={() => navigation.navigate("ItineraryView", { tripId })}
            testID="view-itinerary-link"
          >
            <Text style={styles.viewItineraryLink}>View itinerary →</Text>
          </Pressable>
        )}
      </View>

      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(m) => m.id}
        contentContainerStyle={styles.messages}
        renderItem={({ item }) => (
          <ChatBubble role={item.role} text={item.text} testID={`chat-bubble-${item.id}`} />
        )}
      />

      {generating && (
        <View style={styles.typingRow} testID="chat-generating-indicator">
          <ActivityIndicator size="small" color={colors.primary} />
          <Text style={styles.typingText}>Planning…</Text>
        </View>
      )}

      {missingFields && (
        <View style={styles.clarifyPanel} testID="clarification-panel">
          {missingFields.includes("budget") && (
            <TextInput
              style={styles.input}
              placeholder="Budget (INR)"
              placeholderTextColor={colors.textMuted}
              keyboardType="numeric"
              value={clarifyBudget}
              onChangeText={setClarifyBudget}
              testID="clarify-budget-input"
            />
          )}
          {missingFields.includes("dates") && (
            <View style={styles.row}>
              <TextInput
                style={[styles.input, styles.rowItem]}
                placeholder="Start (YYYY-MM-DD)"
                placeholderTextColor={colors.textMuted}
                value={clarifyStart}
                onChangeText={setClarifyStart}
                testID="clarify-start-input"
              />
              <TextInput
                style={[styles.input, styles.rowItem]}
                placeholder="End (YYYY-MM-DD)"
                placeholderTextColor={colors.textMuted}
                value={clarifyEnd}
                onChangeText={setClarifyEnd}
                testID="clarify-end-input"
              />
            </View>
          )}
          <Pressable
            style={styles.clarifyButton}
            onPress={handleClarifySubmit}
            testID="clarify-submit-button"
          >
            <Text style={styles.clarifyButtonText}>Continue planning</Text>
          </Pressable>
        </View>
      )}

      <View style={styles.composerRow}>
        <TextInput
          style={styles.composerInput}
          placeholder={hasItinerary ? "Ask for a change…" : "Planning your trip…"}
          placeholderTextColor={colors.textMuted}
          value={draft}
          onChangeText={setDraft}
          editable={hasItinerary && !sending}
          testID="chat-composer-input"
        />
        <Pressable
          style={[styles.sendButton, (!draft.trim() || sending) && styles.sendButtonDisabled]}
          onPress={() => void handleSend()}
          disabled={!draft.trim() || sending}
          testID="chat-send-button"
        >
          <Text style={styles.sendButtonText}>{sending ? "…" : "Send"}</Text>
        </Pressable>
      </View>
      </KeyboardAvoidingView>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    padding: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  title: { ...typography.subtitle, color: colors.text },
  viewItineraryLink: { ...typography.caption, color: colors.primary, fontWeight: "600" },
  messages: { padding: spacing.lg, gap: spacing.xs, flexGrow: 1 },
  typingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },
  typingText: { ...typography.caption, color: colors.textMuted },
  clarifyPanel: {
    padding: spacing.md,
    gap: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    backgroundColor: colors.surface,
  },
  row: { flexDirection: "row", gap: spacing.sm },
  rowItem: { flex: 1 },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    padding: spacing.sm,
    color: colors.text,
    ...typography.body,
  },
  clarifyButton: {
    backgroundColor: colors.primary,
    borderRadius: radius.md,
    padding: spacing.sm + 2,
    alignItems: "center",
  },
  clarifyButtonText: { ...typography.subtitle, color: colors.primaryText },
  composerRow: {
    flexDirection: "row",
    gap: spacing.sm,
    padding: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  composerInput: {
    flex: 1,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    color: colors.text,
    ...typography.body,
  },
  sendButton: {
    backgroundColor: colors.primary,
    borderRadius: radius.lg,
    paddingHorizontal: spacing.md,
    alignItems: "center",
    justifyContent: "center",
  },
  sendButtonDisabled: { opacity: 0.5 },
  sendButtonText: { ...typography.subtitle, color: colors.primaryText },
});
