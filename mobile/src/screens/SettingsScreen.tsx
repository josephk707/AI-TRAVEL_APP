import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { GradientBackground } from "../components/GradientBackground";
import { ScreenHeader } from "../components/ScreenHeader";
import { SUPPORTED_LANGUAGES, useTranslation } from "../i18n";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { colors, radius, spacing, typography } from "../theme/tokens";

export function SettingsScreen(): React.JSX.Element {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList, "Settings">>();
  const insets = useSafeAreaInsets();
  const { signOut } = useAuth();
  const { t, language } = useTranslation();
  const [signingOut, setSigningOut] = useState(false);

  const currentLanguageLabel =
    SUPPORTED_LANGUAGES.find((l) => l.code === language)?.nativeLabel ?? language;

  const rows: {
    icon: keyof typeof Ionicons.glyphMap;
    label: string;
    value?: string;
    onPress: () => void;
  }[] = [
    {
      icon: "language-outline",
      label: t("settings.language"),
      value: currentLanguageLabel,
      onPress: () => navigation.navigate("LanguageSettings"),
    },
    {
      icon: "notifications-outline",
      label: t("settings.notifications"),
      onPress: () => navigation.navigate("Notifications"),
    },
  ];

  return (
    <GradientBackground>
      <StatusBar style="light" />
      <View style={{ paddingTop: insets.top + spacing.sm }}>
        <ScreenHeader title={t("settings.title")} />
      </View>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.sectionLabel}>{t("settings.general")}</Text>
        <Card style={styles.rowsCard} variant="flat">
          {rows.map((row, index) => (
            <Pressable
              key={row.label}
              onPress={row.onPress}
              accessibilityRole="button"
              style={({ pressed }) => [
                styles.row,
                index < rows.length - 1 && styles.rowDivider,
                pressed && styles.rowPressed,
              ]}
              testID={`settings-row-${row.label}`}
            >
              <View style={styles.rowIconBadge}>
                <Ionicons name={row.icon} size={18} color={colors.primary} />
              </View>
              <Text style={styles.rowLabel}>{row.label}</Text>
              {row.value ? <Text style={styles.rowValue}>{row.value}</Text> : null}
              <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
            </Pressable>
          ))}
        </Card>

        <Text style={styles.sectionLabel}>{t("settings.account")}</Text>
        <Card variant="flat">
          <Button
            label={signingOut ? t("common.signingOut") : t("common.signOut")}
            onPress={() => {
              setSigningOut(true);
              void signOut();
            }}
            disabled={signingOut}
            variant="secondary"
            testID="settings-sign-out-button"
          />
        </Card>
      </ScrollView>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, paddingHorizontal: spacing.lg, paddingBottom: spacing.xl, gap: spacing.md },
  sectionLabel: { ...typography.captionMedium, color: colors.textMuted, marginTop: spacing.sm },
  rowsCard: { padding: 0, overflow: "hidden" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
  },
  rowDivider: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  rowPressed: { backgroundColor: colors.surfaceAlt },
  rowIconBadge: {
    width: 34,
    height: 34,
    borderRadius: radius.md,
    backgroundColor: colors.primarySoft,
    alignItems: "center",
    justifyContent: "center",
  },
  rowLabel: { ...typography.bodyMedium, color: colors.text, flex: 1 },
  rowValue: { ...typography.caption, color: colors.textMuted },
});
