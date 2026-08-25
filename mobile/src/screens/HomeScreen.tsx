import React, { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";

import { bootstrapSession, fetchMyProfile, ProfileData } from "../api/auth";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LoadingView } from "../components/LoadingView";
import { colors, spacing, typography } from "../theme/tokens";

type ProfileLoadState =
  | { status: "loading" }
  | { status: "success"; profile: ProfileData }
  | { status: "error"; message: string };

/**
 * The authenticated landing screen. This is Phase 3's actual proof point:
 * a real mobile session token round-trips through FastAPI's cryptographic
 * JWT verification and comes back with this exact user's own row from
 * Postgres — POST /auth/session/bootstrap (idempotent load-or-create)
 * followed by GET /auth/me (docs/API_SPECIFICATION.md §2).
 *
 * Deliberately not a product screen — no trips, no AI, no maps (Phase 4+).
 */
export function HomeScreen(): React.JSX.Element {
  const { user, signOut } = useAuth();
  const [profileState, setProfileState] = useState<ProfileLoadState>({ status: "loading" });
  const [signingOut, setSigningOut] = useState(false);

  const loadProfile = useCallback(() => {
    bootstrapSession()
      .then(() => fetchMyProfile())
      .then((profile) => setProfileState({ status: "success", profile }))
      .catch((error: unknown) => {
        const message =
          error instanceof ApiError
            ? error.message
            : "Unexpected error while loading your profile.";
        setProfileState({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const handleRetry = useCallback(() => {
    setProfileState({ status: "loading" });
    loadProfile();
  }, [loadProfile]);

  const handleSignOut = useCallback(() => {
    setSigningOut(true);
    void signOut();
  }, [signOut]);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <StatusBar style="auto" />
      <Text style={styles.title}>Welcome</Text>
      <Text style={styles.subtitle}>{user?.email ?? "Signed in"}</Text>

      <Card style={styles.card}>
        <Text style={styles.cardTitle}>Your profile</Text>

        {profileState.status === "loading" && <LoadingView label="Loading your profile…" />}

        {profileState.status === "success" && (
          <View testID="profile-success">
            <Text style={styles.detail}>User ID: {profileState.profile.id}</Text>
            <Text style={styles.detail}>Role: {profileState.profile.role}</Text>
            <Text style={styles.detail}>
              Onboarding:{" "}
              {profileState.profile.onboarding_completed_at ? "complete" : "not started"}
            </Text>
          </View>
        )}

        {profileState.status === "error" && (
          <View testID="profile-error">
            <Text style={styles.errorText}>{profileState.message}</Text>
            <View style={styles.retryButton}>
              <Button label="Retry" onPress={handleRetry} testID="profile-retry-button" />
            </View>
          </View>
        )}
      </Card>

      <View style={styles.signOutButton}>
        <Button
          label={signingOut ? "Signing out…" : "Sign out"}
          onPress={handleSignOut}
          disabled={signingOut}
          testID="sign-out-button"
        />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    backgroundColor: colors.background,
    padding: spacing.lg,
    gap: spacing.md,
  },
  title: { ...typography.title, color: colors.text },
  subtitle: { ...typography.body, color: colors.textMuted, marginBottom: spacing.md },
  card: { gap: spacing.sm },
  cardTitle: { ...typography.subtitle, color: colors.text },
  errorText: { ...typography.subtitle, color: colors.error },
  detail: { ...typography.caption, color: colors.textMuted, marginTop: spacing.xs },
  retryButton: { marginTop: spacing.md, alignSelf: "flex-start" },
  signOutButton: { alignSelf: "flex-start", marginTop: spacing.sm },
});
