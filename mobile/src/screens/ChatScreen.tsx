import { Ionicons } from "@expo/vector-icons";
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

import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError } from "../api/client";
import {
  fetchTrip,
  generateItinerary,
  modifyItinerary,
  updateTrip,
  type GenerateItineraryResult,
  type ItineraryDay,
} from "../api/trips";
import { ChatBubble } from "../components/ChatBubble";
import { Screen } from "../components/Screen";
import { ScreenHeader } from "../components/ScreenHeader";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { radius, spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";

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

/** A compact, readable rendering of the generated plan for the chat
 * transcript — one line per day — so the traveller sees what the AI
 * proposed without leaving the conversation. The full timeline (with
 * navigation, costs and flags) lives on ItineraryView. */
export function describePlan(days: ItineraryDay[]): string | null {
  const lines = days
    .filter((day) => day.items.length > 0)
    .map((day) => {
      const stops = day.items
        .filter((item) => item.status !== "skipped")
        .map((item) =>
          item.planned_start ? `${item.poi_name ?? "stop"} (${item.planned_start})` : (item.poi_name ?? "stop"),
        )
        .join(", ");
      return `Day ${day.day_number}${day.date ? ` · ${day.date}` : ""}: ${stops}`;
    });
  return lines.length > 0 ? lines.join("\n") : null;
}

/** F3 (initial generation) + F5 (conversational modification) — the
 * "conversational planner, primary interaction surface" (MOBILE_ARCHITECTURE.md
 * §2/§25). Generation runs automatically on first entry; every message
 * after that is a scoped modification request. */
export function ChatScreen(): React.JSX.Element {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList, "Chat">>();
  const route = useRoute<RouteProp<RootStackParamList, "Chat">>();
  const { tripId, interests, useOwnIdeas } = route.params;
  const { colors, isDark } = useTheme();
  const styles = useThemedStyles(createStyles);
  const insets = useSafeAreaInsets();

  const [messages, setMessages] = useState<Message[]>([]);
  const [destinationLabel, setDestinationLabel] = useState<string | null>(null);
  const [clarifyDestination, setClarifyDestination] = useState("");
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
    async (overrides?: {
      budget?: number;
      start_date?: string;
      end_date?: string;
      destination?: string;
    }) => {
      setGenerating(true);
      setMissingFields(null);
      try {
        if (
          overrides &&
          (overrides.budget || overrides.start_date || overrides.end_date || overrides.destination)
        ) {
          await updateTrip(tripId, {
            budget_planned: overrides.budget,
            start_date: overrides.start_date,
            end_date: overrides.end_date,
            destination: overrides.destination,
          });
          if (overrides.destination) setDestinationLabel(overrides.destination);
        }
        const result = await generateItinerary(tripId, {
          interests,
          use_own_ideas: useOwnIdeas,
          budget: overrides?.budget,
          destination: overrides?.destination,
          time_window:
            overrides?.start_date && overrides?.end_date
              ? { start: overrides.start_date, end: overrides.end_date }
              : undefined,
        });
        setHasItinerary(true);
        appendAssistant(summarize(result));
        const plan = describePlan(result.days);
        if (plan) appendAssistant(plan);
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
        setDestinationLabel(trip.destination);
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
      destination: clarifyDestination.trim() || undefined,
    });
  }, [runGeneration, clarifyBudget, clarifyStart, clarifyEnd, clarifyDestination]);

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

  const canSend = !!draft.trim() && !sending;

  return (
    <Screen>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={80}
      >
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <ScreenHeader
          title="Trip planner"
          subtitle={destinationLabel ?? undefined}
          rightAction={
            hasItinerary ? (
              <Pressable
                onPress={() => navigation.navigate("ItineraryView", { tripId })}
                style={({ pressed }) => [styles.viewItineraryButton, pressed && styles.linkPressed]}
                accessibilityRole="button"
                testID="view-itinerary-link"
              >
                <Text style={styles.viewItineraryLink}>View itinerary →</Text>
              </Pressable>
            ) : undefined
          }
        />
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
          <ActivityIndicator size="small" color={colors.text} />
          <Text style={styles.typingText}>Planning…</Text>
        </View>
      )}

      {missingFields && (
        <View style={styles.clarifyPanel} testID="clarification-panel">
          {missingFields.includes("destination") && (
            <TextInput
              style={styles.input}
              placeholder="Destination (city, country)"
              placeholderTextColor={colors.textFaint}
              keyboardAppearance={isDark ? "dark" : "light"}
              value={clarifyDestination}
              onChangeText={setClarifyDestination}
              testID="clarify-destination-input"
            />
          )}
          {missingFields.includes("budget") && (
            <TextInput
              style={styles.input}
              placeholder="Budget (INR)"
              placeholderTextColor={colors.textFaint}
              keyboardAppearance={isDark ? "dark" : "light"}
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
                placeholderTextColor={colors.textFaint}
                keyboardAppearance={isDark ? "dark" : "light"}
                value={clarifyStart}
                onChangeText={setClarifyStart}
                testID="clarify-start-input"
              />
              <TextInput
                style={[styles.input, styles.rowItem]}
                placeholder="End (YYYY-MM-DD)"
                placeholderTextColor={colors.textFaint}
                keyboardAppearance={isDark ? "dark" : "light"}
                value={clarifyEnd}
                onChangeText={setClarifyEnd}
                testID="clarify-end-input"
              />
            </View>
          )}
          <Pressable
            style={({ pressed }) => [styles.clarifyButton, pressed && styles.clarifyButtonPressed]}
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
          placeholderTextColor={colors.textFaint}
          keyboardAppearance={isDark ? "dark" : "light"}
          value={draft}
          onChangeText={setDraft}
          editable={hasItinerary && !sending}
          testID="chat-composer-input"
        />
        <Pressable
          style={({ pressed }) => [
            styles.sendButton,
            !canSend && styles.sendButtonDisabled,
            pressed && canSend && styles.sendButtonPressed,
          ]}
          onPress={() => void handleSend()}
          disabled={!canSend}
          accessibilityRole="button"
          accessibilityLabel="Send"
          accessibilityState={{ disabled: !canSend }}
          testID="chat-send-button"
        >
          {sending ? (
            <ActivityIndicator size="small" color={colors.primaryText} />
          ) : (
            <Ionicons name="arrow-up" size={20} color={colors.primaryText} />
          )}
        </Pressable>
      </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    flex: { flex: 1 },
    header: {
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: colors.border,
    },
    viewItineraryButton: {
      paddingVertical: spacing.sm,
      paddingHorizontal: spacing.sm + 2,
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: colors.borderStrong,
    },
    viewItineraryLink: { ...typography.captionMedium, color: colors.text },
    linkPressed: { opacity: 0.6 },
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
      backgroundColor: colors.surfaceAlt,
    },
    row: { flexDirection: "row", gap: spacing.sm },
    rowItem: { flex: 1 },
    input: {
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
      borderRadius: radius.md,
      padding: spacing.sm + 2,
      color: colors.text,
      ...typography.body,
    },
    clarifyButton: {
      backgroundColor: colors.primary,
      borderRadius: radius.md,
      padding: spacing.sm + 2,
      alignItems: "center",
    },
    clarifyButtonPressed: { backgroundColor: colors.primaryStrong, opacity: 0.9 },
    clarifyButtonText: { ...typography.subtitle, color: colors.primaryText },
    composerRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: spacing.sm,
      padding: spacing.md,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: colors.border,
    },
    composerInput: {
      flex: 1,
      minHeight: 44,
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
      borderRadius: radius.md,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm,
      color: colors.text,
      ...typography.body,
    },
    sendButton: {
      width: 44,
      height: 44,
      borderRadius: radius.pill,
      backgroundColor: colors.primary,
      alignItems: "center",
      justifyContent: "center",
    },
    sendButtonPressed: { backgroundColor: colors.primaryStrong, opacity: 0.9 },
    sendButtonDisabled: { opacity: 0.4 },
  });
