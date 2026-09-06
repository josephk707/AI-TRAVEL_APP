import { Ionicons } from "@expo/vector-icons";
import { useRoute } from "@react-navigation/native";
import type { RouteProp } from "@react-navigation/native";
import React, { useCallback, useEffect, useState } from "react";
import { Alert, FlatList, Pressable, Share, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError } from "../api/client";
import {
  addTrustedContact,
  listTrustedContacts,
  startLocationShare,
  stopLocationShare,
  triggerSos,
  TrustedContact,
} from "../api/safety";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ErrorState } from "../components/ErrorState";
import { LoadingView } from "../components/LoadingView";
import { Screen } from "../components/Screen";
import { ScreenHeader } from "../components/ScreenHeader";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { radius, spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";

type LoadState =
  | { status: "loading" }
  | { status: "success"; contacts: TrustedContact[] }
  | { status: "error"; message: string };

/** F21 — Safety/SOS Trusted-Contact Sharing. Location sharing here is
 * strictly opt-in per trip (§27) — nothing is shared until the traveller
 * explicitly taps "Start sharing," and it can be stopped instantly. */
export function SafetyScreen(): React.JSX.Element {
  const route = useRoute<RouteProp<RootStackParamList, "Safety">>();
  const { tripId } = route.params;
  const insets = useSafeAreaInsets();
  const { colors, isDark } = useTheme();
  const styles = useThemedStyles(createStyles);

  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [sharing, setSharing] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [shareError, setShareError] = useState<string | null>(null);
  const [sosSending, setSosSending] = useState(false);
  const [sosError, setSosError] = useState<string | null>(null);
  const [sosSent, setSosSent] = useState(false);

  const resolveContacts = useCallback(async (): Promise<LoadState> => {
    try {
      const contacts = await listTrustedContacts();
      return { status: "success", contacts };
    } catch (error) {
      return {
        status: "error",
        message: error instanceof ApiError ? error.message : "Couldn't load your trusted contacts.",
      };
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    resolveContacts().then((result) => {
      if (!cancelled) setState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [resolveContacts]);

  const load = useCallback(() => {
    setState({ status: "loading" });
    void resolveContacts().then(setState);
  }, [resolveContacts]);

  const handleAddContact = useCallback(async () => {
    setAddError(null);
    try {
      await addTrustedContact(name.trim(), phone.trim() || undefined);
      setName("");
      setPhone("");
      load();
    } catch (error) {
      setAddError(error instanceof ApiError ? error.message : "Couldn't add that contact.");
    }
  }, [name, phone, load]);

  const handleStartSharing = useCallback(async () => {
    setShareError(null);
    try {
      const result = await startLocationShare(tripId);
      setSharing(true);
      setShareUrl(result.share_url);
      void Share.share({ message: `Follow my trip live on Yatra AI: ${result.share_url}` });
    } catch (error) {
      setShareError(error instanceof ApiError ? error.message : "Couldn't start location sharing.");
    }
  }, [tripId]);

  const handleStopSharing = useCallback(async () => {
    try {
      await stopLocationShare(tripId);
      setSharing(false);
      setShareUrl(null);
    } catch (error) {
      setShareError(error instanceof ApiError ? error.message : "Couldn't stop location sharing.");
    }
  }, [tripId]);

  const handleSos = useCallback(() => {
    Alert.alert(
      "Send SOS alert?",
      "This notifies your trusted contacts immediately with your last known location.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Send SOS",
          style: "destructive",
          onPress: async () => {
            setSosSending(true);
            setSosError(null);
            try {
              await triggerSos(tripId);
              setSosSent(true);
            } catch (error) {
              setSosError(error instanceof ApiError ? error.message : "Couldn't send the SOS alert.");
            } finally {
              setSosSending(false);
            }
          },
        },
      ],
    );
  }, [tripId]);

  return (
    <Screen>
      <View style={[styles.flex, { paddingTop: insets.top + spacing.sm }]}>
      <ScreenHeader title="Safety" />

      <Pressable
        style={({ pressed }) => [
          styles.sosButton,
          sosSending && styles.sosButtonDisabled,
          pressed && !sosSending && styles.sosButtonPressed,
        ]}
        onPress={handleSos}
        disabled={sosSending}
        testID="sos-button"
        accessibilityRole="button"
      >
        <Ionicons name="alert-circle" size={24} color={colors.background} />
        <Text style={styles.sosButtonText}>{sosSending ? "Sending…" : "SOS"}</Text>
      </Pressable>
      {sosSent && (
        <Text style={styles.sosSentText} testID="sos-sent-text">
          Alert sent — your trusted contacts are being notified.
        </Text>
      )}
      {sosError && <Text style={styles.errorText}>{sosError}</Text>}

      <Card style={styles.shareCard}>
        <Text style={styles.cardTitle}>Share my location for this trip</Text>
        {sharing ? (
          <>
            <Text style={styles.cardHint}>Your trusted contacts can see this trip live.</Text>
            <Button label="Stop sharing" onPress={() => void handleStopSharing()} testID="stop-share-button" />
          </>
        ) : (
          <Button label="Start sharing" onPress={() => void handleStartSharing()} testID="start-share-button" />
        )}
        {shareUrl && (
          <Text style={styles.shareUrl} testID="share-url-display">
            {shareUrl}
          </Text>
        )}
        {shareError && <Text style={styles.errorText}>{shareError}</Text>}
      </Card>

      {state.status === "loading" && (
        <View style={styles.centered}>
          <LoadingView label="Loading your trusted contacts…" />
        </View>
      )}

      {state.status === "error" && (
        <View style={styles.centered} testID="safety-error">
          <ErrorState message={state.message} retryLabel="Retry" onRetry={load} testID="safety-retry-button" />
        </View>
      )}

      {state.status === "success" && (
        <FlatList
          testID="safety-content"
          data={state.contacts}
          keyExtractor={(c) => c.id}
          contentContainerStyle={styles.list}
          ListHeaderComponent={
            <Card style={styles.addCard}>
              <Text style={styles.cardTitle}>Add a trusted contact</Text>
              <TextInput
                style={styles.input}
                placeholder="Name"
                placeholderTextColor={colors.textFaint}
                keyboardAppearance={isDark ? "dark" : "light"}
                value={name}
                onChangeText={setName}
                testID="contact-name-input"
              />
              <TextInput
                style={styles.input}
                placeholder="Phone number"
                placeholderTextColor={colors.textFaint}
                keyboardAppearance={isDark ? "dark" : "light"}
                keyboardType="phone-pad"
                value={phone}
                onChangeText={setPhone}
                testID="contact-phone-input"
              />
              <Button label="Add contact" onPress={() => void handleAddContact()} testID="add-contact-button" />
              {addError && <Text style={styles.errorText}>{addError}</Text>}
              <Text style={[styles.cardTitle, styles.contactsHeading]}>
                Trusted contacts ({state.contacts.length})
              </Text>
            </Card>
          }
          ListEmptyComponent={
            <Text style={styles.emptyText} testID="contacts-empty">
              No trusted contacts added yet.
            </Text>
          }
          renderItem={({ item }) => (
            <View style={styles.contactRow} testID={`contact-${item.id}`}>
              <View style={styles.contactIcon}>
                <Ionicons name="person-outline" size={16} color={colors.text} />
              </View>
              <Text style={styles.contactText}>{item.name}</Text>
            </View>
          )}
        />
      )}
      </View>
    </Screen>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    flex: { flex: 1 },
    centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
    errorText: { ...typography.body, color: colors.error, marginHorizontal: spacing.lg },
    // SOS is the one place on this screen that keeps a semantic fill — it is
    // an emergency action and the red carries meaning, not decoration.
    sosButton: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "center",
      gap: spacing.xs,
      backgroundColor: colors.error,
      borderRadius: radius.lg,
      marginHorizontal: spacing.lg,
      paddingVertical: spacing.md,
    },
    sosButtonPressed: { opacity: 0.85 },
    sosButtonDisabled: { opacity: 0.6 },
    sosButtonText: { ...typography.subtitle, color: colors.background },
    sosSentText: {
      ...typography.caption,
      color: colors.success,
      textAlign: "center",
      marginTop: spacing.xs,
    },
    shareCard: { margin: spacing.lg, gap: spacing.sm },
    cardTitle: { ...typography.subtitle, color: colors.text },
    cardHint: { ...typography.caption, color: colors.textMuted },
    shareUrl: {
      ...typography.captionMedium,
      color: colors.text,
      backgroundColor: colors.surfaceAlt,
      borderWidth: 1,
      borderColor: colors.border,
      padding: spacing.sm,
      borderRadius: radius.sm,
    },
    list: { padding: spacing.lg, paddingTop: 0, gap: spacing.sm },
    addCard: { gap: spacing.sm },
    contactsHeading: { marginTop: spacing.md },
    input: {
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
      borderRadius: radius.md,
      padding: spacing.sm + 2,
      color: colors.text,
      ...typography.body,
    },
    emptyText: { ...typography.body, color: colors.textMuted },
    contactRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: spacing.sm,
      backgroundColor: colors.surface,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      padding: spacing.md,
      marginBottom: spacing.xs,
    },
    contactIcon: {
      width: 32,
      height: 32,
      borderRadius: radius.pill,
      backgroundColor: colors.surfaceAlt,
      borderWidth: 1,
      borderColor: colors.border,
      alignItems: "center",
      justifyContent: "center",
    },
    contactText: { ...typography.body, color: colors.text },
  });
