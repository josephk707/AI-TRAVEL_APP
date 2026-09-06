import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { StatusBar } from "expo-status-bar";
import React, { useCallback, useEffect, useState } from "react";
import { Alert, FlatList, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { ApiError } from "../api/client";
import {
  Collection,
  createCollection,
  Favorite,
  listCollections,
  listFavorites,
} from "../api/collections";
import { Button } from "../components/Button";
import { ErrorState } from "../components/ErrorState";
import { GradientBackground } from "../components/GradientBackground";
import { LoadingView } from "../components/LoadingView";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { colors, radius, spacing, typography } from "../theme/tokens";

type LoadState =
  | { status: "loading" }
  | { status: "success"; favorites: Favorite[]; collections: Collection[] }
  | { status: "error"; message: string };

/** F13 — Collections & Favourites. Every favorite/collection here is a
 * real personalization signal read by the recommendation engine
 * (AI_ARCHITECTURE.md §7/§20), not merely a local bookmark. */
export function CollectionsScreen(): React.JSX.Element {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList, "Collections">>();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [newCollectionName, setNewCollectionName] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    setState({ status: "loading" });
    Promise.all([listFavorites(), listCollections()])
      .then(([favorites, collections]) => setState({ status: "success", favorites, collections }))
      .catch((error: unknown) => {
        const message = error instanceof ApiError ? error.message : "Couldn't load your collections.";
        setState({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    const unsubscribe = navigation.addListener("focus", load);
    return unsubscribe;
  }, [navigation, load]);

  const createNewCollection = useCallback(async () => {
    if (!newCollectionName.trim()) return;
    setCreating(true);
    try {
      await createCollection(newCollectionName.trim());
      setNewCollectionName("");
      load();
    } catch (error) {
      Alert.alert(
        "Couldn't create collection",
        error instanceof ApiError ? error.message : "Please try again.",
      );
    } finally {
      setCreating(false);
    }
  }, [newCollectionName, load]);

  return (
    <GradientBackground>
      <View style={styles.flex}>
      <StatusBar style="light" />
      <View style={styles.header}>
        <Text style={styles.title}>Saved places</Text>
      </View>

      {state.status === "loading" && (
        <View style={styles.centered}>
          <LoadingView label="Loading your saved places…" />
        </View>
      )}

      {state.status === "error" && (
        <View style={styles.centered} testID="collections-error">
          <ErrorState message={state.message} retryLabel="Retry" onRetry={load} testID="collections-retry-button" />
        </View>
      )}

      {state.status === "success" && (
        <FlatList
          testID="collections-content"
          data={state.collections}
          keyExtractor={(collection) => collection.id}
          contentContainerStyle={styles.list}
          ListHeaderComponent={
            <View style={styles.section}>
              <Text style={styles.sectionHeading}>Favorites ({state.favorites.length})</Text>
              {state.favorites.length === 0 ? (
                <Text style={styles.emptyText} testID="favorites-empty">
                  No favorites yet — tap the heart on any place to save it.
                </Text>
              ) : (
                state.favorites.map((favorite) => (
                  <View key={favorite.poi_id} style={styles.row} testID={`favorite-${favorite.poi_id}`}>
                    <Ionicons name="heart" size={18} color={colors.error} />
                    <Text style={styles.rowText}>{favorite.poi_name}</Text>
                  </View>
                ))
              )}

              <Text style={[styles.sectionHeading, styles.collectionsHeading]}>Collections</Text>
              <View style={styles.newCollectionRow}>
                <TextInput
                  style={styles.input}
                  placeholder="New collection name"
                  placeholderTextColor={colors.textMuted}
                  value={newCollectionName}
                  onChangeText={setNewCollectionName}
                  testID="new-collection-input"
                />
                <Button
                  label={creating ? "Creating…" : "Create"}
                  onPress={() => void createNewCollection()}
                  disabled={creating}
                  testID="create-collection-button"
                />
              </View>
            </View>
          }
          ListEmptyComponent={
            <Text style={styles.emptyText} testID="collections-empty">
              No collections yet.
            </Text>
          }
          renderItem={({ item }) => (
            <Pressable style={styles.row} testID={`collection-${item.id}`}>
              <Ionicons name="albums-outline" size={18} color={colors.primary} />
              <Text style={styles.rowText}>
                {item.name} ({item.item_count})
              </Text>
            </Pressable>
          )}
        />
      )}
      </View>
    </GradientBackground>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  header: { padding: spacing.lg, paddingBottom: spacing.sm },
  title: { ...typography.title, color: colors.text },
  centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
  errorText: { ...typography.body, color: colors.error, textAlign: "center" },
  emptyText: { ...typography.body, color: colors.textMuted, marginBottom: spacing.sm },
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.sm },
  section: { gap: spacing.xs },
  sectionHeading: { ...typography.subtitle, color: colors.text, marginTop: spacing.md },
  collectionsHeading: { marginTop: spacing.lg },
  newCollectionRow: { flexDirection: "row", gap: spacing.sm, alignItems: "center", marginBottom: spacing.sm },
  input: {
    flex: 1,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.sm + 2,
    color: colors.text,
    ...typography.body,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.md,
    marginBottom: spacing.xs,
  },
  rowText: { ...typography.body, color: colors.text },
});
