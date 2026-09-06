import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useTranslation } from "../i18n";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { radius, spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";

type NavTarget = keyof Pick<RootStackParamList, "Home" | "TripsList" | "Explore" | "Profile">;

/**
 * Persistent bottom navigation — visual + UX improvement per this phase's
 * scope. Deliberately implemented as a plain component calling
 * `navigation.navigate()` between four SIBLING screens already registered
 * in the existing single stack (RootNavigator), rather than restructuring
 * the app into a nested Tab.Navigator: native-stack's own `navigate()`
 * (unlike `push()`) already jumps to an existing instance of a route
 * already in the stack instead of piling up duplicates, which gives
 * genuine tab-like switching behavior without touching the navigation
 * dependencies of the other ~20 screens already wired to
 * RootStackParamList. Documented decision, CLAUDE.md §13.
 *
 * The elevated center button starts AI trip planning directly
 * (TripCreation) rather than linking to Chat, which requires a `tripId`
 * this bar has no way to supply — never a fake/mismatched destination.
 */
export function BottomNavBar({ active }: { active: NavTarget }): React.JSX.Element {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const insets = useSafeAreaInsets();
  const { t } = useTranslation();
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);

  const items: { target: NavTarget; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
    { target: "Home", label: t("nav.home"), icon: "home" },
    { target: "TripsList", label: t("nav.trips"), icon: "airplane" },
    { target: "Explore", label: t("nav.explore"), icon: "compass" },
    { target: "Profile", label: t("nav.profile"), icon: "person" },
  ];
  const midpoint = 2;

  return (
    <View style={[styles.container, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
      <View style={styles.bar}>
        {items.slice(0, midpoint).map((item) => (
          <NavItem
            key={item.target}
            {...item}
            isActive={active === item.target}
            navigation={navigation}
          />
        ))}

        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("nav.assistant")}
          onPress={() => navigation.navigate("TripCreation")}
          style={({ pressed }) => [styles.centerButton, pressed && styles.centerPressed]}
          testID="nav-assistant-button"
        >
          <Ionicons name="sparkles" size={22} color={colors.primaryText} />
        </Pressable>

        {items.slice(midpoint).map((item) => (
          <NavItem
            key={item.target}
            {...item}
            isActive={active === item.target}
            navigation={navigation}
          />
        ))}
      </View>
    </View>
  );
}

function NavItem({
  target,
  label,
  icon,
  isActive,
  navigation,
}: {
  target: NavTarget;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  isActive: boolean;
  navigation: NativeStackNavigationProp<RootStackParamList>;
}): React.JSX.Element {
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ selected: isActive }}
      onPress={() => navigation.navigate(target)}
      style={({ pressed }) => [styles.navItem, pressed && styles.pressed]}
      testID={`nav-${label.toLowerCase()}-button`}
    >
      <Ionicons
        name={isActive ? icon : (`${icon}-outline` as keyof typeof Ionicons.glyphMap)}
        size={22}
        color={isActive ? colors.text : colors.textFaint}
      />
      <Text style={[styles.navLabel, isActive && styles.navLabelActive]}>{label}</Text>
    </Pressable>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    container: {
      backgroundColor: colors.backgroundElevated,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: colors.borderStrong,
    },
    bar: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-around",
      paddingTop: spacing.sm,
      paddingHorizontal: spacing.sm,
    },
    navItem: { alignItems: "center", justifyContent: "center", gap: 2, minWidth: 56 },
    navLabel: { ...typography.micro, color: colors.textFaint, textTransform: "none" },
    navLabelActive: { color: colors.text },
    centerButton: {
      marginTop: -24,
      width: 56,
      height: 56,
      borderRadius: radius.pill,
      backgroundColor: colors.primary,
      alignItems: "center",
      justifyContent: "center",
      borderWidth: 4,
      borderColor: colors.backgroundElevated,
    },
    centerPressed: { opacity: 0.85 },
    pressed: { opacity: 0.6 },
  });
