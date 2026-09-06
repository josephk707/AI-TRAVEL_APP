import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Screen } from "../components/Screen";
import { ScreenHeader } from "../components/ScreenHeader";
import { SUPPORTED_LANGUAGES, useTranslation } from "../i18n";
import type { RootStackParamList } from "../navigation/RootNavigator";
import {
  radius,
  spacing,
  THEME_MODES,
  type Theme,
  type ThemeMode,
  typography,
  useTheme,
  useThemedStyles,
} from "../theme";

const APPEARANCE_ICONS: Record<ThemeMode, keyof typeof Ionicons.glyphMap> = {
  system: "phone-portrait-outline",
  light: "sunny-outline",
  dark: "moon-outline",
};

const APPEARANCE_LABEL_KEYS: Record<ThemeMode, string> = {
  system: "settings.appearanceSystem",
  light: "settings.appearanceLight",
  dark: "settings.appearanceDark",
};

export function SettingsScreen(): React.JSX.Element {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList, "Settings">>();
  const insets = useSafeAreaInsets();
  const { signOut } = useAuth();
  const { t, language } = useTranslation();
  const { colors, mode, setMode } = useTheme();
  const styles = useThemedStyles(createStyles);
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
    <Screen>
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
                <Ionicons name={row.icon} size={18} color={colors.text} />
              </View>
              <Text style={styles.rowLabel}>{row.label}</Text>
              {row.value ? <Text style={styles.rowValue}>{row.value}</Text> : null}
              <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
            </Pressable>
          ))}
        </Card>

        <Text style={styles.sectionLabel}>{t("settings.appearance")}</Text>
        <Card variant="flat" style={styles.appearanceCard}>
          <View style={styles.segmented} accessibilityRole="radiogroup">
            {THEME_MODES.map((option) => {
              const selected = mode === option;
              return (
                <Pressable
                  key={option}
                  accessibilityRole="radio"
                  accessibilityState={{ selected, checked: selected }}
                  accessibilityLabel={t(APPEARANCE_LABEL_KEYS[option])}
                  onPress={() => {
                    void setMode(option);
                  }}
                  style={({ pressed }) => [
                    styles.segment,
                    selected && styles.segmentSelected,
                    pressed && !selected && styles.segmentPressed,
                  ]}
                  testID={`settings-appearance-${option}`}
                >
                  <Ionicons
                    name={APPEARANCE_ICONS[option]}
                    size={18}
                    color={selected ? colors.primaryText : colors.textMuted}
                  />
                  <Text style={[styles.segmentLabel, selected && styles.segmentLabelSelected]}>
                    {t(APPEARANCE_LABEL_KEYS[option])}
                  </Text>
                </Pressable>
              );
            })}
          </View>
          <Text style={styles.hint}>{t("settings.appearanceHint")}</Text>
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
    sectionLabel: {
      ...typography.micro,
      color: colors.textMuted,
      textTransform: "uppercase",
      marginTop: spacing.sm,
    },
    rowsCard: { padding: 0, overflow: "hidden" },
    row: {
      flexDirection: "row",
      alignItems: "center",
      gap: spacing.sm,
      paddingVertical: spacing.md,
      paddingHorizontal: spacing.md,
    },
    rowDivider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
    rowPressed: { backgroundColor: colors.surfaceAlt },
    rowIconBadge: {
      width: 34,
      height: 34,
      borderRadius: radius.sm,
      backgroundColor: colors.surfaceAlt,
      borderWidth: 1,
      borderColor: colors.border,
      alignItems: "center",
      justifyContent: "center",
    },
    rowLabel: { ...typography.bodyMedium, color: colors.text, flex: 1 },
    rowValue: { ...typography.caption, color: colors.textMuted },
    appearanceCard: { padding: spacing.md, gap: spacing.sm },
    segmented: {
      flexDirection: "row",
      backgroundColor: colors.surfaceAlt,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      padding: 3,
      gap: 3,
    },
    segment: {
      flex: 1,
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "center",
      gap: spacing.xs + 2,
      paddingVertical: spacing.sm + 2,
      borderRadius: radius.sm + 1,
    },
    segmentSelected: { backgroundColor: colors.primary },
    segmentPressed: { backgroundColor: colors.surfaceHighlight },
    segmentLabel: { ...typography.captionMedium, color: colors.textMuted },
    segmentLabelSelected: { color: colors.primaryText },
    hint: { ...typography.caption, color: colors.textFaint },
  });
