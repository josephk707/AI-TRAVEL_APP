import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";

import { useAuth } from "../auth/AuthContext";
import { colors, radius, spacing, typography } from "../theme/tokens";

/**
 * The mobile app's entry point for anyone without a session
 * (MOBILE_ARCHITECTURE.md §2's AuthStack). Google OAuth via Supabase Auth
 * is the ONLY sign-in path — no password fields, no "skip sign-in", no
 * locally fabricated session (CLAUDE.md §5).
 */
export function SignInScreen(): React.JSX.Element {
  const { state, errorMessage, signInWithGoogle, clearError } = useAuth();
  const isBusy = state === "AUTHENTICATING";

  return (
    <View style={styles.container}>
      <StatusBar style="dark" />

      <View style={styles.hero}>
        <View style={styles.logoBadge}>
          <Ionicons name="compass" size={40} color={colors.primaryText} />
        </View>
        <Text style={styles.title}>AI Tourist Guide</Text>
        <Text style={styles.subtitle}>Your personal travel companion, wherever you go.</Text>
      </View>

      <View style={styles.footer}>
        {state === "SESSION_EXPIRED" && (
          <Text style={styles.noticeText} testID="session-expired-notice">
            Your session expired. Please sign in again.
          </Text>
        )}

        {state === "AUTH_ERROR" && errorMessage && (
          <Text style={styles.errorText} testID="auth-error-notice">
            {errorMessage}
          </Text>
        )}

        <Pressable
          accessibilityRole="button"
          accessibilityState={{ disabled: isBusy, busy: isBusy }}
          testID="google-sign-in-button"
          disabled={isBusy}
          onPress={() => {
            clearError();
            void signInWithGoogle();
          }}
          style={({ pressed }) => [
            styles.googleButton,
            pressed && !isBusy && styles.googleButtonPressed,
            isBusy && styles.googleButtonDisabled,
          ]}
        >
          {isBusy ? (
            <ActivityIndicator size="small" color={colors.text} />
          ) : (
            <Ionicons name="logo-google" size={20} color={colors.text} />
          )}
          <Text style={styles.googleButtonLabel}>
            {isBusy ? "Signing in…" : "Continue with Google"}
          </Text>
        </Pressable>

        <Text style={styles.legalText}>
          By continuing, you agree that your Google account is used solely to create and secure
          your AI Tourist Guide account.
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
    justifyContent: "space-between",
    padding: spacing.xl,
  },
  hero: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.md,
  },
  logoBadge: {
    width: 72,
    height: 72,
    borderRadius: radius.lg,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  title: { ...typography.title, color: colors.text, textAlign: "center" },
  subtitle: {
    ...typography.body,
    color: colors.textMuted,
    textAlign: "center",
    maxWidth: 280,
  },
  footer: { gap: spacing.md, paddingBottom: spacing.lg },
  noticeText: {
    ...typography.body,
    color: colors.warning,
    textAlign: "center",
  },
  errorText: {
    ...typography.body,
    color: colors.error,
    textAlign: "center",
  },
  googleButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    backgroundColor: colors.background,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingVertical: spacing.sm + 4,
    paddingHorizontal: spacing.lg,
  },
  googleButtonPressed: { backgroundColor: colors.surface },
  googleButtonDisabled: { opacity: 0.6 },
  googleButtonLabel: { ...typography.subtitle, color: colors.text },
  legalText: {
    ...typography.caption,
    color: colors.textMuted,
    textAlign: "center",
  },
});
