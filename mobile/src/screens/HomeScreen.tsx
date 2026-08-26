import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { StatusBar } from "expo-status-bar";

import { bootstrapSession, fetchMyProfile, ProfileData } from "../api/auth";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { LoadingView } from "../components/LoadingView";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { colors, radius, spacing, typography } from "../theme/tokens";

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
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList, "Home">>();
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

      <Pressable
        style={({ pressed }) => [styles.exploreCard, pressed && styles.exploreCardPressed]}
        onPress={() => navigation.navigate("TripsList")}
        accessibilityRole="button"
        testID="my-trips-button"
      >
        <View style={styles.exploreIconBadge}>
          <Ionicons name="airplane-outline" size={24} color={colors.primaryText} />
        </View>
        <View style={styles.exploreTextGroup}>
          <Text style={styles.exploreTitle}>Plan a trip</Text>
          <Text style={styles.exploreSubtitle}>
            Let Yatra AI build you a personalised itinerary
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
      </Pressable>

      <Pressable
        style={({ pressed }) => [styles.exploreCard, pressed && styles.exploreCardPressed]}
        onPress={() => navigation.navigate("Explore")}
        accessibilityRole="button"
        testID="explore-places-button"
      >
        <View style={styles.exploreIconBadge}>
          <Ionicons name="map-outline" size={24} color={colors.primaryText} />
        </View>
        <View style={styles.exploreTextGroup}>
          <Text style={styles.exploreTitle}>Explore places</Text>
          <Text style={styles.exploreSubtitle}>Search heritage sites, food, and more nearby</Text>
        </View>
        <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
      </Pressable>

      <Pressable
        style={({ pressed }) => [styles.exploreCard, pressed && styles.exploreCardPressed]}
        onPress={() => navigation.navigate("Translate")}
        accessibilityRole="button"
        testID="translate-button"
      >
        <View style={styles.exploreIconBadge}>
          <Ionicons name="language-outline" size={24} color={colors.primaryText} />
        </View>
        <View style={styles.exploreTextGroup}>
          <Text style={styles.exploreTitle}>Translate a phrase</Text>
          <Text style={styles.exploreSubtitle}>Hindi, Telugu, Malayalam, Kannada, and more</Text>
        </View>
        <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
      </Pressable>

      <Pressable
        style={({ pressed }) => [styles.exploreCard, pressed && styles.exploreCardPressed]}
        onPress={() => navigation.navigate("Collections")}
        accessibilityRole="button"
        testID="saved-places-button"
      >
        <View style={styles.exploreIconBadge}>
          <Ionicons name="heart-outline" size={24} color={colors.primaryText} />
        </View>
        <View style={styles.exploreTextGroup}>
          <Text style={styles.exploreTitle}>Saved places</Text>
          <Text style={styles.exploreSubtitle}>Your favorites and collections</Text>
        </View>
        <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
      </Pressable>

      <Pressable
        style={({ pressed }) => [styles.exploreCard, pressed && styles.exploreCardPressed]}
        onPress={() => navigation.navigate("Notifications")}
        accessibilityRole="button"
        testID="notifications-button"
      >
        <View style={styles.exploreIconBadge}>
          <Ionicons name="notifications-outline" size={24} color={colors.primaryText} />
        </View>
        <View style={styles.exploreTextGroup}>
          <Text style={styles.exploreTitle}>Notifications</Text>
          <Text style={styles.exploreSubtitle}>Arrivals, reminders, and updates</Text>
        </View>
        <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
      </Pressable>

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
  exploreCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.md,
  },
  exploreCardPressed: { opacity: 0.85 },
  exploreIconBadge: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  exploreTextGroup: { flex: 1, gap: 2 },
  exploreTitle: { ...typography.subtitle, color: colors.text },
  exploreSubtitle: { ...typography.caption, color: colors.textMuted },
  signOutButton: { alignSelf: "flex-start", marginTop: spacing.sm },
});
