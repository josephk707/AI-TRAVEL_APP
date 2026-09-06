import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { bootstrapSession, fetchMyProfile, ProfileData } from "../api/auth";
import { ApiError } from "../api/client";
import { BottomNavBar } from "../components/BottomNavBar";
import { Card } from "../components/Card";
import { ErrorState } from "../components/ErrorState";
import { IconBadge } from "../components/IconBadge";
import { LoadingView } from "../components/LoadingView";
import { Screen } from "../components/Screen";
import { useTranslation } from "../i18n";
import type { RootStackParamList } from "../navigation/RootNavigator";
import {
  radius,
  spacing,
  type Theme,
  typography,
  useResponsive,
  useTheme,
  useThemedStyles,
} from "../theme";

type ProfileLoadState =
  | { status: "loading" }
  | { status: "success"; profile: ProfileData }
  | { status: "error"; message: string };

/**
 * The authenticated landing screen — the app's home hub, rendered in the
 * minimal monochrome visual language while keeping its real data flow
 * (POST /auth/session/bootstrap -> GET /auth/me) exactly as-is.
 */
export function HomeScreen(): React.JSX.Element {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList, "Home">>();
  const { t, syncFromServerProfile } = useTranslation();
  const [profileState, setProfileState] = useState<ProfileLoadState>({ status: "loading" });
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);
  const responsive = useResponsive();
  // Two columns of action tiles once there is room (tablet / browser);
  // a single stacked list on phones.
  const actionColumns = responsive.columnsFor(300, spacing.sm);
  const actionWidth = responsive.itemWidthFor(actionColumns, spacing.sm, spacing.lg);

  const loadProfile = useCallback(() => {
    bootstrapSession()
      .then(() => fetchMyProfile())
      .then((profile) => {
        setProfileState({ status: "success", profile });
        // First-run/new-device language reconciliation — see
        // LanguageContext's documented rule.
        syncFromServerProfile(profile.preferred_language);
      })
      .catch((error: unknown) => {
        const message = error instanceof ApiError ? error.message : t("common.somethingWentWrong");
        setProfileState({ status: "error", message });
      });
  }, [syncFromServerProfile, t]);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const handleRetry = useCallback(() => {
    setProfileState({ status: "loading" });
    loadProfile();
  }, [loadProfile]);

  const displayName =
    profileState.status === "success" ? profileState.profile.display_name : null;

  const actions: {
    icon: keyof typeof Ionicons.glyphMap;
    title: string;
    subtitle: string;
    onPress: () => void;
    testID: string;
  }[] = [
    {
      icon: "airplane-outline",
      title: t("home.planTrip"),
      subtitle: t("home.planTripSubtitle"),
      onPress: () => navigation.navigate("TripCreation"),
      testID: "my-trips-button",
    },
    {
      icon: "flash-outline",
      title: t("home.quickPlan"),
      subtitle: t("home.quickPlanSubtitle"),
      onPress: () => navigation.navigate("QuickPlan"),
      testID: "quick-plan-button",
    },
    {
      icon: "map-outline",
      title: t("home.explorePlaces"),
      subtitle: t("home.explorePlacesSubtitle"),
      onPress: () => navigation.navigate("Explore"),
      testID: "explore-places-button",
    },
    {
      icon: "language-outline",
      title: t("home.translate"),
      subtitle: t("home.translateSubtitle"),
      onPress: () => navigation.navigate("Translate"),
      testID: "translate-button",
    },
    {
      icon: "heart-outline",
      title: t("home.savedPlaces"),
      subtitle: t("home.savedPlacesSubtitle"),
      onPress: () => navigation.navigate("Collections"),
      testID: "saved-places-button",
    },
    {
      icon: "notifications-outline",
      title: t("home.notifications"),
      subtitle: t("home.notificationsSubtitle"),
      onPress: () => navigation.navigate("Notifications"),
      testID: "notifications-button",
    },
  ];

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={[styles.container, { paddingTop: insets.top + spacing.md }]}
      >
        <View>
          <Text style={styles.greeting}>
            {t("home.greeting")}
            {displayName ? `, ${displayName}` : ""} 👋
          </Text>
          <Text style={styles.subtitle}>{t("home.subtitlePrompt")}</Text>
        </View>

        <Card style={styles.card} variant="flat">
          <Text style={styles.cardTitle}>{t("home.yourProfile")}</Text>

          {profileState.status === "loading" && <LoadingView label={t("home.loadingProfile")} />}

          {profileState.status === "success" && (
            <View testID="profile-success" style={styles.profileRow}>
              <Text style={styles.detail}>
                {t("home.role")}: {profileState.profile.role}
              </Text>
              <Text style={styles.detail}>
                {t("home.onboarding")}:{" "}
                {profileState.profile.onboarding_completed_at
                  ? t("home.complete")
                  : t("home.notStarted")}
              </Text>
            </View>
          )}

          {profileState.status === "error" && (
            <View testID="profile-error">
              <ErrorState
                message={profileState.message}
                retryLabel={t("common.retry")}
                onRetry={handleRetry}
                testID="profile-retry-button"
              />
            </View>
          )}
        </Card>

        <View style={[styles.actionsList, actionColumns > 1 && styles.actionsGrid]}>
          {actions.map((action) => (
            <Pressable
              key={action.testID}
              style={({ pressed }) => [
                styles.actionCard,
                actionColumns > 1 && { width: actionWidth },
                pressed && styles.actionCardPressed,
              ]}
              onPress={action.onPress}
              accessibilityRole="button"
              testID={action.testID}
            >
              <IconBadge icon={action.icon} />
              <View style={styles.actionTextGroup}>
                <Text style={styles.actionTitle}>{action.title}</Text>
                <Text style={styles.actionSubtitle}>{action.subtitle}</Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={colors.textFaint} />
            </Pressable>
          ))}
        </View>
      </ScrollView>
      <BottomNavBar active="Home" />
    </Screen>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    container: {
      flexGrow: 1,
      paddingHorizontal: spacing.lg,
      paddingBottom: spacing.xl,
      gap: spacing.md,
    },
    greeting: { ...typography.title, color: colors.text },
    subtitle: { ...typography.body, color: colors.textMuted, marginTop: spacing.xs },
    card: { gap: spacing.sm },
    cardTitle: { ...typography.subtitle, color: colors.text },
    profileRow: { gap: spacing.xs },
    detail: { ...typography.caption, color: colors.textMuted },
    actionsList: { gap: spacing.sm },
    actionsGrid: { flexDirection: "row", flexWrap: "wrap" },
    actionCard: {
      flexDirection: "row",
      alignItems: "center",
      gap: spacing.sm,
      backgroundColor: colors.surface,
      borderRadius: radius.lg,
      borderWidth: 1,
      borderColor: colors.border,
      padding: spacing.md,
    },
    actionCardPressed: { backgroundColor: colors.surfaceAlt },
    actionTextGroup: { flex: 1, gap: 2 },
    actionTitle: { ...typography.subtitle, color: colors.text },
    actionSubtitle: { ...typography.caption, color: colors.textMuted },
  });
