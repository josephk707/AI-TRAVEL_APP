import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { fetchMyProfile, ProfileData } from "../api/auth";
import { ApiError } from "../api/client";
import { fetchTravelDna, TravelDna } from "../api/personalization";
import { useAuth } from "../auth/AuthContext";
import { BottomNavBar } from "../components/BottomNavBar";
import { Card } from "../components/Card";
import { ErrorState } from "../components/ErrorState";
import { LoadingView } from "../components/LoadingView";
import { Screen } from "../components/Screen";
import { useTranslation } from "../i18n";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { radius, spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";

type LoadState =
  | { status: "loading" }
  | { status: "success"; profile: ProfileData }
  | { status: "error"; message: string };

type DnaLoadState =
  | { status: "loading" }
  | { status: "success"; dna: TravelDna }
  | { status: "error"; message: string };

export function ProfileScreen(): React.JSX.Element {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList, "Profile">>();
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { t } = useTranslation();
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);
  const [state, setState] = useState<LoadState>({ status: "loading" });

  // Resolves the next state without setting it itself (matches
  // PoiDetailScreen.tsx's resolveDetail/loadState split) so the mount
  // effect only ever calls setState inside a .then() callback.
  const resolveProfile = useCallback(async (): Promise<LoadState> => {
    try {
      const profile = await fetchMyProfile();
      return { status: "success", profile };
    } catch (error) {
      const message = error instanceof ApiError ? error.message : t("common.somethingWentWrong");
      return { status: "error", message };
    }
  }, [t]);

  useEffect(() => {
    let cancelled = false;
    resolveProfile().then((result) => {
      if (!cancelled) setState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [resolveProfile]);

  const load = useCallback(() => {
    setState({ status: "loading" });
    void resolveProfile().then(setState);
  }, [resolveProfile]);

  const [dnaState, setDnaState] = useState<DnaLoadState>({ status: "loading" });

  const resolveDna = useCallback(async (): Promise<DnaLoadState> => {
    try {
      const dna = await fetchTravelDna();
      return { status: "success", dna };
    } catch (error) {
      const message = error instanceof ApiError ? error.message : t("common.somethingWentWrong");
      return { status: "error", message };
    }
  }, [t]);

  useEffect(() => {
    let cancelled = false;
    resolveDna().then((result) => {
      if (!cancelled) setDnaState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [resolveDna]);

  const loadDna = useCallback(() => {
    setDnaState({ status: "loading" });
    void resolveDna().then(setDnaState);
  }, [resolveDna]);

  const displayName = state.status === "success" ? state.profile.display_name : null;
  const initial = (displayName ?? user?.email ?? "?").trim().charAt(0).toUpperCase();

  const links: { icon: keyof typeof Ionicons.glyphMap; label: string; onPress: () => void }[] = [
    { icon: "airplane-outline", label: t("profile.myTrips"), onPress: () => navigation.navigate("TripsList") },
    { icon: "heart-outline", label: t("profile.savedPlaces"), onPress: () => navigation.navigate("Collections") },
    {
      icon: "notifications-outline",
      label: t("profile.notifications"),
      onPress: () => navigation.navigate("Notifications"),
    },
    { icon: "settings-outline", label: t("profile.settings"), onPress: () => navigation.navigate("Settings") },
  ];

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={[
          styles.container,
          { paddingTop: insets.top + spacing.md, paddingBottom: spacing.xl },
        ]}
      >
        <Text style={styles.title}>{t("profile.title")}</Text>

        {state.status === "loading" && (
          <Card style={styles.centerCard} variant="flat">
            <LoadingView label={t("home.loadingProfile")} />
          </Card>
        )}

        {state.status === "error" && (
          <Card style={styles.centerCard} variant="flat">
            <ErrorState message={state.message} retryLabel={t("common.retry")} onRetry={load} />
          </Card>
        )}

        {state.status === "success" && (
          <Card style={styles.identityCard} variant="flat" testID="profile-success">
            <View style={styles.avatar}>
              <Text style={styles.avatarLabel}>{initial}</Text>
            </View>
            <View style={styles.identityText}>
              <Text style={styles.name}>{displayName ?? user?.email ?? "Traveller"}</Text>
              {user?.email ? <Text style={styles.email}>{user.email}</Text> : null}
            </View>
          </Card>
        )}

        <Text style={styles.sectionLabel}>Your Travel DNA</Text>
        {dnaState.status === "loading" && (
          <Card style={styles.centerCard} variant="flat" testID="travel-dna-loading">
            <LoadingView label="Building your Travel DNA…" />
          </Card>
        )}
        {dnaState.status === "error" && (
          <Card style={styles.centerCard} variant="flat" testID="travel-dna-error">
            <ErrorState message={dnaState.message} retryLabel={t("common.retry")} onRetry={loadDna} />
          </Card>
        )}
        {dnaState.status === "success" && (
          <View style={styles.dnaCard} testID="travel-dna-success">
            <View style={styles.dnaHeader}>
              <Ionicons name="sparkles" size={20} color={colors.text} />
              <Text style={styles.dnaPersonality}>{dnaState.dna.travel_personality}</Text>
            </View>
            <Text style={styles.dnaSummary}>{dnaState.dna.summary}</Text>
            <View style={styles.dnaStatsRow}>
              <View style={styles.dnaStat}>
                <Text style={styles.dnaStatValue}>{dnaState.dna.trips_planned}</Text>
                <Text style={styles.dnaStatLabel}>Trips planned</Text>
              </View>
              <View style={styles.dnaStat}>
                <Text style={styles.dnaStatValue}>{dnaState.dna.places_saved}</Text>
                <Text style={styles.dnaStatLabel}>Places saved</Text>
              </View>
            </View>
            {dnaState.dna.interests.length > 0 && (
              <View style={styles.dnaChipRow}>
                {dnaState.dna.interests.slice(0, 4).map((interest) => (
                  <View key={interest} style={styles.dnaChip}>
                    <Text style={styles.dnaChipText}>{interest}</Text>
                  </View>
                ))}
              </View>
            )}
            {dnaState.dna.generated_by === "template" && (
              <Text style={styles.dnaHint}>
                Keep exploring and telling us your preferences — your Travel DNA gets richer
                as you go.
              </Text>
            )}
          </View>
        )}

        <Text style={styles.sectionLabel}>{t("profile.accountSection")}</Text>
        <Card style={styles.linksCard} variant="flat">
          {links.map((link, index) => (
            <Pressable
              key={link.label}
              onPress={link.onPress}
              accessibilityRole="button"
              style={({ pressed }) => [
                styles.linkRow,
                index < links.length - 1 && styles.linkRowDivider,
                pressed && styles.linkRowPressed,
              ]}
            >
              <View style={styles.linkIconBadge}>
                <Ionicons name={link.icon} size={18} color={colors.text} />
              </View>
              <Text style={styles.linkLabel}>{link.label}</Text>
              <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
            </Pressable>
          ))}
        </Card>
      </ScrollView>
      <BottomNavBar active="Profile" />
    </Screen>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    container: { flexGrow: 1, paddingHorizontal: spacing.lg, gap: spacing.md },
    title: { ...typography.title, color: colors.text },
    centerCard: { alignItems: "center", paddingVertical: spacing.xl },
    identityCard: { flexDirection: "row", alignItems: "center", gap: spacing.md },
    avatar: {
      width: 60,
      height: 60,
      borderRadius: radius.pill,
      backgroundColor: colors.surfaceAlt,
      borderWidth: 1,
      borderColor: colors.border,
      alignItems: "center",
      justifyContent: "center",
    },
    avatarLabel: { ...typography.title, color: colors.text },
    identityText: { flex: 1, gap: 2 },
    name: { ...typography.h1, color: colors.text },
    email: { ...typography.caption, color: colors.textMuted },
    sectionLabel: {
      ...typography.micro,
      color: colors.textMuted,
      textTransform: "uppercase",
      marginTop: spacing.sm,
    },
    dnaCard: {
      backgroundColor: colors.surface,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.border,
      padding: spacing.lg,
      gap: spacing.sm,
    },
    dnaHeader: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
    dnaPersonality: { ...typography.h1, color: colors.text },
    dnaSummary: { ...typography.body, color: colors.textMuted },
    dnaStatsRow: { flexDirection: "row", gap: spacing.lg, marginTop: spacing.xs },
    dnaStat: { gap: 2 },
    dnaStatValue: { ...typography.h2, color: colors.text },
    dnaStatLabel: { ...typography.caption, color: colors.textMuted },
    dnaChipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, marginTop: spacing.xs },
    dnaChip: {
      backgroundColor: colors.surfaceAlt,
      borderWidth: 1,
      borderColor: colors.border,
      borderRadius: radius.pill,
      paddingVertical: spacing.xs,
      paddingHorizontal: spacing.sm,
    },
    dnaChipText: { ...typography.captionMedium, color: colors.text },
    dnaHint: { ...typography.caption, color: colors.textFaint, marginTop: spacing.xs },
    linksCard: { padding: 0, overflow: "hidden" },
    linkRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: spacing.sm,
      paddingVertical: spacing.md,
      paddingHorizontal: spacing.md,
    },
    linkRowDivider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
    linkRowPressed: { backgroundColor: colors.surfaceAlt },
    linkIconBadge: {
      width: 34,
      height: 34,
      borderRadius: radius.sm,
      backgroundColor: colors.surfaceAlt,
      borderWidth: 1,
      borderColor: colors.border,
      alignItems: "center",
      justifyContent: "center",
    },
    linkLabel: { ...typography.bodyMedium, color: colors.text, flex: 1 },
  });
