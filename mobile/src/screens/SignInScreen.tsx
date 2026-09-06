import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useAuth } from "../auth/AuthContext";
import { GradientBackground } from "../components/GradientBackground";
import { IconBadge } from "../components/IconBadge";
import { useTranslation } from "../i18n";
import { colors, radius, spacing, typography } from "../theme/tokens";

/**
 * The mobile app's entry point for anyone without a session
 * (MOBILE_ARCHITECTURE.md §2's AuthStack). Google OAuth via Supabase Auth
 * is the ONLY sign-in path — no password fields, no "skip sign-in", no
 * locally fabricated session (CLAUDE.md §5).
 */
export function SignInScreen(): React.JSX.Element {
  const { state, errorMessage, signInWithGoogle, clearError } = useAuth();
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const isBusy = state === "AUTHENTICATING";

  return (
    <GradientBackground>
      <StatusBar style="light" />
      <View style={[styles.container, { paddingTop: insets.top + spacing.xl }]}>
        <View style={styles.hero}>
          <IconBadge icon="airplane" size={80} variant="gradient" />
          <Text style={styles.brand}>Yatra AI</Text>
          <Text style={styles.title}>{t("auth.tagline")}</Text>
          <Text style={styles.subtitle}>{t("auth.subtitle")}</Text>
        </View>

        <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.lg }]}>
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
              <ActivityIndicator size="small" color={colors.background} />
            ) : (
              <Ionicons name="logo-google" size={20} color={colors.background} />
            )}
            <Text style={styles.googleButtonLabel}>
              {isBusy ? t("auth.signingIn") : t("auth.continueWithGoogle")}
            </Text>
          </Pressable>

          <Text style={styles.legalText}>
            By continuing, you agree that your Google account is used solely to create and secure
            your Yatra AI account.
          </Text>
        </View>
      </View>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: "space-between",
    paddingHorizontal: spacing.xl,
  },
  hero: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
  },
  brand: { ...typography.h1, color: colors.text, marginTop: spacing.md },
  title: { ...typography.title, color: colors.text, textAlign: "center", marginTop: spacing.xs },
  subtitle: {
    ...typography.body,
    color: colors.textMuted,
    textAlign: "center",
    maxWidth: 300,
    marginTop: spacing.xs,
  },
  footer: { gap: spacing.md },
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
    backgroundColor: colors.white,
    borderRadius: radius.pill,
    paddingVertical: spacing.sm + 4,
    paddingHorizontal: spacing.lg,
  },
  googleButtonPressed: { opacity: 0.9 },
  googleButtonDisabled: { opacity: 0.6 },
  googleButtonLabel: { ...typography.subtitle, color: colors.background },
  legalText: {
    ...typography.caption,
    color: colors.textFaint,
    textAlign: "center",
  },
});
