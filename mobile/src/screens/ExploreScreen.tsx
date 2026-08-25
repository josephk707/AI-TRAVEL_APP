import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import React, { useCallback, useEffect, useState } from "react";
import {
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import MapView, { Marker, PROVIDER_GOOGLE } from "react-native-maps";
import { StatusBar } from "expo-status-bar";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import type { Poi, PoiCategory } from "../api/pois";
import { ApiError } from "../api/client";
import { searchPois } from "../api/pois";
import { LoadingView } from "../components/LoadingView";
import { MapErrorBoundary } from "../components/MapErrorBoundary";
import { PoiCard } from "../components/PoiCard";
import { SelectableChip } from "../components/SelectableChip";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { colors, radius, spacing, typography } from "../theme/tokens";

type LoadState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; pois: Poi[]; degraded: boolean; message: string | null }
  | { status: "error"; message: string };

const CATEGORY_FILTERS: { value: PoiCategory; label: string }[] = [
  { value: "heritage", label: "Heritage" },
  { value: "restaurant", label: "Food & Drink" },
  { value: "attraction", label: "Attraction" },
  { value: "nature", label: "Nature" },
  { value: "shopping", label: "Shopping" },
];

// India-wide default map framing (this product's launch region — see
// DATABASE_SCHEMA.md's `pois.country default 'India'`) — used only until
// the user has searched, and never overwritten with a fabricated
// "current location" (no location permission has been requested here;
// that is F7's scope, not F6's).
const DEFAULT_REGION = {
  latitude: 22.3511,
  longitude: 78.6677,
  latitudeDelta: 20,
  longitudeDelta: 20,
};

/** F6 — Maps & Navigation. Standalone POI search/browse experience
 * (search + category filter + map/list toggle), reachable from HomeScreen.
 * Interim placement per docs/PHASE_STATUS.md's Phase 5 section: the
 * blueprint's documented host screens (ItineraryViewScreen,
 * OnTripCompanionScreen) don't exist yet (F3/F7) — this screen is the
 * genuine, reachable, working home for the map/POI feature until those
 * screens exist to embed it into. */
export function ExploreScreen(): React.JSX.Element {
  const navigation =
    useNavigation<NativeStackNavigationProp<RootStackParamList, "Explore">>();
  const insets = useSafeAreaInsets();
  const [queryText, setQueryText] = useState("");
  const [category, setCategory] = useState<PoiCategory | null>(null);
  const [viewMode, setViewMode] = useState<"list" | "map">("list");
  const [loadState, setLoadState] = useState<LoadState>({ status: "idle" });

  // Resolves the next LoadState without setting state itself, so the
  // category-change effect below can set state only inside a .then()
  // callback (react-hooks/set-state-in-effect) while handleSubmit — a
  // real event handler, not an effect — is free to set "loading"
  // synchronously before calling this (same split as
  // InterestSelectScreen.tsx's resolveInterests/loadInterests).
  const resolveSearch = useCallback(
    async (searchText: string, cat: PoiCategory | null): Promise<LoadState> => {
      if (!searchText.trim()) return { status: "idle" };
      try {
        const result = await searchPois({ query: searchText.trim(), category: cat ?? undefined });
        return {
          status: "success",
          pois: result.pois,
          degraded: result.degraded,
          message: result.message,
        };
      } catch (error) {
        return {
          status: "error",
          message:
            error instanceof ApiError ? error.message : "Couldn't search places right now.",
        };
      }
    },
    [],
  );

  // Re-run automatically when the category filter changes on an already
  // -submitted search, so toggling a chip doesn't require re-pressing
  // search — but typing a brand-new query only searches on submit
  // (avoids firing a request per keystroke).
  useEffect(() => {
    if (loadState.status === "idle" || !queryText.trim()) return;
    let cancelled = false;
    resolveSearch(queryText, category).then((result) => {
      if (!cancelled) setLoadState(result);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category]);

  const handleSubmit = useCallback(() => {
    if (!queryText.trim()) {
      setLoadState({ status: "idle" });
      return;
    }
    setLoadState({ status: "loading" });
    void resolveSearch(queryText, category).then(setLoadState);
  }, [queryText, category, resolveSearch]);

  const toggleCategory = useCallback((value: PoiCategory) => {
    setCategory((current) => (current === value ? null : value));
  }, []);

  const openDetail = useCallback(
    (poiId: string) => {
      navigation.navigate("PoiDetail", { poiId });
    },
    [navigation],
  );

  const results = loadState.status === "success" ? loadState.pois : [];

  return (
    <View style={[styles.container, { paddingTop: insets.top + spacing.md }]}>
      <StatusBar style="dark" />

      <View style={styles.header}>
        <Text style={styles.title}>Explore places</Text>
        <View style={styles.searchRow}>
          <View style={styles.searchInputWrapper}>
            <Ionicons name="search" size={18} color={colors.textMuted} />
            <TextInput
              testID="explore-search-input"
              style={styles.searchInput}
              placeholder="Search heritage sites, restaurants, markets…"
              placeholderTextColor={colors.textMuted}
              value={queryText}
              onChangeText={setQueryText}
              onSubmitEditing={handleSubmit}
              returnKeyType="search"
            />
          </View>
          <Pressable
            testID="explore-view-toggle"
            style={styles.viewToggle}
            accessibilityRole="button"
            onPress={() => setViewMode((mode) => (mode === "list" ? "map" : "list"))}
          >
            <Ionicons
              name={viewMode === "list" ? "map-outline" : "list-outline"}
              size={20}
              color={colors.primaryText}
            />
          </Pressable>
        </View>

        <FlatList
          horizontal
          data={CATEGORY_FILTERS}
          keyExtractor={(item) => item.value}
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.filterRow}
          renderItem={({ item }) => (
            <SelectableChip
              label={item.label}
              selected={category === item.value}
              onPress={() => toggleCategory(item.value)}
              testID={`explore-category-${item.value}`}
            />
          )}
        />
      </View>

      {loadState.status === "idle" && (
        <View style={styles.centerFill} testID="explore-empty-prompt">
          <Ionicons name="compass-outline" size={40} color={colors.textMuted} />
          <Text style={styles.emptyText}>Search to discover places for your trip.</Text>
        </View>
      )}

      {loadState.status === "loading" && (
        <View style={styles.centerFill}>
          <LoadingView label="Searching…" />
        </View>
      )}

      {loadState.status === "error" && (
        <View style={styles.centerFill} testID="explore-error">
          <Text style={styles.errorText}>{loadState.message}</Text>
          <Pressable
            style={styles.retryButton}
            onPress={handleSubmit}
            testID="explore-retry-button"
            accessibilityRole="button"
          >
            <Text style={styles.retryLabel}>Retry</Text>
          </Pressable>
        </View>
      )}

      {loadState.status === "success" && results.length === 0 && (
        <View style={styles.centerFill} testID="explore-no-results">
          <Ionicons name="search-outline" size={40} color={colors.textMuted} />
          <Text style={styles.emptyText}>No places found. Try a different search.</Text>
        </View>
      )}

      {loadState.status === "success" && results.length > 0 && (
        <>
          {loadState.degraded && (
            <View style={styles.degradedBanner} testID="explore-degraded-banner">
              <Ionicons name="information-circle-outline" size={16} color={colors.warning} />
              <Text style={styles.degradedText}>
                {loadState.message ?? "Showing curated results only."}
              </Text>
            </View>
          )}

          {viewMode === "list" ? (
            <FlatList
              testID="explore-results-list"
              data={results}
              keyExtractor={(item) => item.id}
              contentContainerStyle={styles.listContent}
              renderItem={({ item }) => (
                <PoiCard
                  poi={item}
                  onPress={() => openDetail(item.id)}
                  testID={`poi-card-${item.id}`}
                />
              )}
            />
          ) : (
            <MapErrorBoundary
              fallback={
                <FlatList
                  testID="explore-results-list"
                  data={results}
                  keyExtractor={(item) => item.id}
                  contentContainerStyle={styles.listContent}
                  renderItem={({ item }) => (
                    <PoiCard
                      poi={item}
                      onPress={() => openDetail(item.id)}
                      testID={`poi-card-${item.id}`}
                    />
                  )}
                />
              }
            >
              <MapView
                testID="explore-map"
                style={styles.map}
                provider={PROVIDER_GOOGLE}
                initialRegion={{
                  latitude: results[0]?.location.lat ?? DEFAULT_REGION.latitude,
                  longitude: results[0]?.location.lng ?? DEFAULT_REGION.longitude,
                  latitudeDelta: 0.2,
                  longitudeDelta: 0.2,
                }}
              >
                {results.map((poi) => (
                  <Marker
                    key={poi.id}
                    testID={`map-marker-${poi.id}`}
                    coordinate={{ latitude: poi.location.lat, longitude: poi.location.lng }}
                    title={poi.name}
                    description={poi.address ?? undefined}
                    onPress={() => openDetail(poi.id)}
                  />
                ))}
              </MapView>
            </MapErrorBoundary>
          )}
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, gap: spacing.sm },
  title: { ...typography.title, color: colors.text },
  searchRow: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  searchInputWrapper: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.sm,
  },
  searchInput: { flex: 1, ...typography.body, color: colors.text, paddingVertical: spacing.sm },
  viewToggle: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
  },
  filterRow: { gap: spacing.xs, paddingVertical: spacing.xs },
  centerFill: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.xl,
  },
  emptyText: { ...typography.body, color: colors.textMuted, textAlign: "center" },
  errorText: { ...typography.body, color: colors.error, textAlign: "center" },
  retryButton: {
    marginTop: spacing.sm,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.lg,
    backgroundColor: colors.primary,
    borderRadius: radius.md,
  },
  retryLabel: { ...typography.body, color: colors.primaryText, fontWeight: "600" },
  listContent: { padding: spacing.lg, gap: spacing.sm },
  map: { flex: 1 },
  degradedBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    marginHorizontal: spacing.lg,
    marginBottom: spacing.xs,
    padding: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: "#FFF6E0",
  },
  degradedText: { ...typography.caption, color: colors.text, flexShrink: 1 },
});
