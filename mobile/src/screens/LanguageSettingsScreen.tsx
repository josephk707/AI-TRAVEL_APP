import { Ionicons } from "@expo/vector-icons";
import React, { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Card } from "../components/Card";
import { GradientBackground } from "../components/GradientBackground";
import { ScreenHeader } from "../components/ScreenHeader";
import { useTranslation, type LanguageCode } from "../i18n";
import { colors, radius, spacing, typography } from "../theme/tokens";

/**
 * The real, working Language Settings screen (Language Settings phase):
 * selecting a language here calls LanguageContext.setLanguage, which (1)
 * applies immediately across the whole app — every screen using
 * useTranslation() re-renders with the new strings the instant this
 * returns, no restart needed, (2) persists locally so it survives app
 * restart, and (3) best-effort syncs to `profiles.preferred_language`
 * server-side, which the AI pipelines (itinerary/chat/quick-plan/
 * narration/photo-Q&A) then read for generated-content language.
 */
export function LanguageSettingsScreen(): React.JSX.Element {
  const insets = useSafeAreaInsets();
  const { t, language, languageOptions, setLanguage } = useTranslation();
  const [pending, setPending] = useState<LanguageCode | null>(null);
  const [syncErrorFor, setSyncErrorFor] = useState<LanguageCode | null>(null);

  const handleSelect = async (code: LanguageCode): Promise<void> => {
    if (code === language) return;
    setPending(code);
    setSyncErrorFor(null);
    const result = await setLanguage(code);
    setPending(null);
    if (!result.syncedToServer) {
      // The local UI language HAS already changed (this is not a failed
      // change) — only the cross-device/account sync didn't complete,
      // which is worth telling the user honestly rather than silently
      // hiding (CLAUDE.md §9).
      setSyncErrorFor(code);
    }
  };

  return (
    <GradientBackground>
      <StatusBar style="light" />
      <View style={{ paddingTop: insets.top + spacing.sm }}>
        <ScreenHeader title={t("languageSettings.title")} />
      </View>
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.subtitle}>{t("languageSettings.subtitle")}</Text>

        <Card style={styles.listCard} variant="flat">
          {languageOptions.map((option, index) => {
            const isActive = option.code === language;
            const isPending = pending === option.code;
            return (
              <Pressable
                key={option.code}
                onPress={() => void handleSelect(option.code)}
                accessibilityRole="radio"
                accessibilityState={{ selected: isActive }}
                disabled={pending !== null}
                style={({ pressed }) => [
                  styles.row,
                  index < languageOptions.length - 1 && styles.rowDivider,
                  pressed && styles.rowPressed,
                ]}
                testID={`language-option-${option.code}`}
              >
                <View style={styles.rowText}>
                  <Text style={styles.nativeLabel}>{option.nativeLabel}</Text>
                  {option.nativeLabel !== option.englishLabel ? (
                    <Text style={styles.englishLabel}>{option.englishLabel}</Text>
                  ) : null}
                  {syncErrorFor === option.code ? (
                    <Text style={styles.syncError}>{t("languageSettings.updateFailed")}</Text>
                  ) : null}
                </View>
                {isPending ? (
                  <Ionicons name="ellipsis-horizontal" size={20} color={colors.textMuted} />
                ) : isActive ? (
                  <View style={styles.checkBadge}>
                    <Ionicons name="checkmark" size={16} color={colors.primaryText} />
                  </View>
                ) : (
                  <View style={styles.uncheckedCircle} />
                )}
              </Pressable>
            );
          })}
        </Card>
      </ScrollView>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  container: { flexGrow: 1, paddingHorizontal: spacing.lg, paddingBottom: spacing.xl, gap: spacing.md },
  subtitle: { ...typography.body, color: colors.textMuted },
  listCard: { padding: 0, overflow: "hidden" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
  },
  rowDivider: { borderBottomWidth: 1, borderBottomColor: colors.divider },
  rowPressed: { backgroundColor: colors.surfaceAlt },
  rowText: { flex: 1, gap: 2 },
  nativeLabel: { ...typography.subtitle, color: colors.text },
  englishLabel: { ...typography.caption, color: colors.textMuted },
  syncError: { ...typography.caption, color: colors.error, marginTop: 2 },
  checkBadge: {
    width: 24,
    height: 24,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  uncheckedCircle: {
    width: 24,
    height: 24,
    borderRadius: radius.pill,
    borderWidth: 2,
    borderColor: colors.borderStrong,
  },
});
