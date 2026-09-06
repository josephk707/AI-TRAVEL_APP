import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import type { Poi, PoiCategory } from "../api/pois";
import { radius, spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";
import { Card } from "./Card";

const CATEGORY_ICON: Record<PoiCategory, React.ComponentProps<typeof Ionicons>["name"]> = {
  heritage: "business-outline",
  restaurant: "restaurant-outline",
  attraction: "camera-outline",
  nature: "leaf-outline",
  shopping: "bag-handle-outline",
  other: "location-outline",
};

const CATEGORY_LABEL: Record<PoiCategory, string> = {
  heritage: "Heritage",
  restaurant: "Food & Drink",
  attraction: "Attraction",
  nature: "Nature",
  shopping: "Shopping",
  other: "Place",
};

interface Props {
  poi: Poi;
  onPress: () => void;
  testID?: string;
}

/** Polished POI result card — used by both the search results list and the
 * (future) itinerary/map marker callout, so the visual language stays
 * consistent wherever a POI is summarized (MOBILE_ARCHITECTURE.md §10). */
export function PoiCard({ poi, onPress, testID }: Props): React.JSX.Element {
  const { colors } = useTheme();
  const styles = useThemedStyles(createStyles);
  const locationLine = [poi.city, poi.region].filter(Boolean).join(", ");

  return (
    <Pressable onPress={onPress} testID={testID} accessibilityRole="button">
      {({ pressed }) => (
        <Card style={[styles.card, pressed && styles.pressed]}>
          <View style={styles.iconBadge}>
            <Ionicons name={CATEGORY_ICON[poi.category]} size={22} color={colors.text} />
          </View>
          <View style={styles.content}>
            <View style={styles.headerRow}>
              <Text style={styles.name} numberOfLines={1}>
                {poi.name}
              </Text>
              {poi.is_heritage_flagship && (
                <View style={styles.flagshipBadge}>
                  <Ionicons name="star" size={11} color={colors.gold} />
                </View>
              )}
            </View>
            <Text style={styles.category}>{CATEGORY_LABEL[poi.category]}</Text>
            {locationLine.length > 0 && (
              <Text style={styles.location} numberOfLines={1}>
                {locationLine}
              </Text>
            )}
          </View>
          <Ionicons name="chevron-forward" size={18} color={colors.textFaint} />
        </Card>
      )}
    </Pressable>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    card: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md },
    pressed: { backgroundColor: colors.surfaceAlt },
    iconBadge: {
      width: 44,
      height: 44,
      borderRadius: radius.md,
      backgroundColor: colors.surfaceAlt,
      borderWidth: 1,
      borderColor: colors.border,
      alignItems: "center",
      justifyContent: "center",
    },
    content: { flex: 1, gap: 2 },
    headerRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
    name: { ...typography.subtitle, color: colors.text, flexShrink: 1 },
    flagshipBadge: {
      width: 18,
      height: 18,
      borderRadius: 9,
      backgroundColor: colors.surfaceAlt,
      alignItems: "center",
      justifyContent: "center",
    },
    category: { ...typography.caption, color: colors.textMuted, fontWeight: "600" },
    location: { ...typography.caption, color: colors.textFaint },
  });
