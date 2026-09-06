import { Ionicons } from "@expo/vector-icons";
import { useRoute } from "@react-navigation/native";
import type { RouteProp } from "@react-navigation/native";
import * as ImagePicker from "expo-image-picker";
import React, { useCallback, useEffect, useState } from "react";
import {
  Alert,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ApiError } from "../api/client";
import {
  createMemoryItem,
  deleteMemoryItem,
  listMemoryItems,
  MemoryItem,
  MemoryItemType,
} from "../api/memory";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingView } from "../components/LoadingView";
import { Screen } from "../components/Screen";
import { ScreenHeader } from "../components/ScreenHeader";
import { supabase } from "../lib/supabase";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { radius, spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";

type LoadState =
  | { status: "loading" }
  | { status: "success"; items: MemoryItem[] }
  | { status: "error"; message: string };

const BUCKET = "memory-items";

function guessContentType(uri: string): { ext: string; contentType: string; itemType: MemoryItemType } {
  const lower = uri.toLowerCase();
  if (lower.endsWith(".png")) return { ext: "png", contentType: "image/png", itemType: "photo" };
  if (lower.endsWith(".mp4") || lower.endsWith(".mov")) {
    return { ext: "mp4", contentType: "video/mp4", itemType: "video" };
  }
  return { ext: "jpg", contentType: "image/jpeg", itemType: "photo" };
}

/** F11 — Trip Memory Box. Photos/videos upload directly from this screen
 * to Supabase Storage (RLS-mediated, migration 20260825120013) — the
 * backend only ever records the resulting metadata, matching
 * app/services/memory_service.py's documented contract. */
export function MemoryBoxScreen(): React.JSX.Element {
  const route = useRoute<RouteProp<RootStackParamList, "MemoryBox">>();
  const { tripId } = route.params;
  const { user } = useAuth();
  const insets = useSafeAreaInsets();
  const { colors, isDark } = useTheme();
  const styles = useThemedStyles(createStyles);

  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [noteText, setNoteText] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const resolveMemories = useCallback(async (): Promise<LoadState> => {
    try {
      const items = await listMemoryItems(tripId);
      return { status: "success", items };
    } catch (error) {
      return {
        status: "error",
        message: error instanceof ApiError ? error.message : "Couldn't load your memories.",
      };
    }
  }, [tripId]);

  useEffect(() => {
    let cancelled = false;
    resolveMemories().then((result) => {
      if (!cancelled) setState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [resolveMemories]);

  const load = useCallback(() => {
    setState({ status: "loading" });
    void resolveMemories().then(setState);
  }, [resolveMemories]);

  const addNote = useCallback(async () => {
    if (!noteText.trim()) return;
    try {
      await createMemoryItem(tripId, { item_type: "note", caption: noteText.trim() });
      setNoteText("");
      load();
    } catch (error) {
      Alert.alert("Couldn't save note", error instanceof ApiError ? error.message : "Please try again.");
    }
  }, [tripId, noteText, load]);

  const pickAndUpload = useCallback(async () => {
    if (!user) return;
    setUploadError(null);
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setUploadError("Photo library access is needed to add a memory.");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({ quality: 0.8 });
    if (result.canceled || !result.assets?.[0]) return;

    const asset = result.assets[0];
    const { ext, contentType, itemType } = guessContentType(asset.uri);
    const storagePath = `${tripId}/${user.id}/${Date.now()}-${Math.random().toString(36).slice(2)}.${ext}`;

    setUploading(true);
    try {
      const response = await fetch(asset.uri);
      const arrayBuffer = await response.arrayBuffer();
      const { error: uploadErr } = await supabase.storage
        .from(BUCKET)
        .upload(storagePath, arrayBuffer, { contentType });
      if (uploadErr) throw uploadErr;

      await createMemoryItem(tripId, { item_type: itemType, storage_path: storagePath });
      load();
    } catch (error) {
      setUploadError(
        error instanceof ApiError ? error.message : "Couldn't upload this memory. Please try again.",
      );
    } finally {
      setUploading(false);
    }
  }, [tripId, user, load]);

  const remove = useCallback(
    (item: MemoryItem) => {
      Alert.alert("Delete memory?", "This can't be undone.", [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            try {
              if (item.storage_path) {
                await supabase.storage.from(BUCKET).remove([item.storage_path]);
              }
              await deleteMemoryItem(tripId, item.id);
              load();
            } catch (error) {
              Alert.alert(
                "Couldn't delete",
                error instanceof ApiError ? error.message : "Please try again.",
              );
            }
          },
        },
      ]);
    },
    [tripId, load],
  );

  return (
    <Screen>
      <View style={[styles.flex, { paddingTop: insets.top + spacing.sm }]}>
      <ScreenHeader title="Memory Box" />

      <View style={styles.composer}>
        <TextInput
          style={styles.noteInput}
          placeholder="Write a quick memory…"
          placeholderTextColor={colors.textFaint}
          keyboardAppearance={isDark ? "dark" : "light"}
          value={noteText}
          onChangeText={setNoteText}
          testID="memory-note-input"
        />
        <View style={styles.composerActions}>
          <Button
            label="Save note"
            onPress={() => void addNote()}
            fullWidth={false}
            testID="memory-save-note-button"
          />
          <Pressable
            style={({ pressed }) => [
              styles.photoButton,
              uploading && styles.photoButtonDisabled,
              pressed && !uploading && styles.photoButtonPressed,
            ]}
            onPress={() => void pickAndUpload()}
            accessibilityRole="button"
            accessibilityState={{ disabled: uploading }}
            testID="memory-add-photo-button"
            disabled={uploading}
          >
            <Ionicons name="camera-outline" size={20} color={colors.text} />
            <Text style={styles.photoButtonText}>{uploading ? "Uploading…" : "Add photo/video"}</Text>
          </Pressable>
        </View>
        {uploadError && (
          <Text style={styles.errorText} testID="memory-upload-error">
            {uploadError}
          </Text>
        )}
      </View>

      {state.status === "loading" && (
        <View style={styles.centered}>
          <LoadingView label="Loading your memories…" />
        </View>
      )}

      {state.status === "error" && (
        <View style={styles.centered} testID="memory-error">
          <ErrorState
            message={state.message}
            retryLabel="Retry"
            onRetry={load}
            testID="memory-retry-button"
          />
        </View>
      )}

      {state.status === "success" && state.items.length === 0 && (
        <View style={styles.centered} testID="memory-empty">
          <EmptyState icon="images-outline" title="No memories saved yet." />
        </View>
      )}

      {state.status === "success" && state.items.length > 0 && (
        <FlatList
          data={state.items}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.list}
          testID="memory-list"
          renderItem={({ item }) => (
            <View style={styles.itemRow} testID={`memory-item-${item.id}`}>
              <View style={styles.itemIcon}>
                <Ionicons
                  name={item.storage_path ? "image-outline" : "document-text-outline"}
                  size={20}
                  color={colors.text}
                />
              </View>
              <View style={styles.itemBody}>
                <Text style={styles.itemCaption}>{item.caption || item.item_type}</Text>
                <Text style={styles.itemMeta}>
                  Saved {new Date(item.uploaded_at).toLocaleDateString()}
                </Text>
              </View>
              <Pressable
                onPress={() => remove(item)}
                accessibilityRole="button"
                accessibilityLabel="Delete memory"
                hitSlop={8}
                style={({ pressed }) => pressed && styles.deletePressed}
                testID={`memory-delete-${item.id}`}
              >
                <Ionicons name="trash-outline" size={20} color={colors.textMuted} />
              </Pressable>
            </View>
          )}
        />
      )}
      </View>
    </Screen>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    flex: { flex: 1 },
    composer: { paddingHorizontal: spacing.lg, gap: spacing.sm },
    noteInput: {
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
      borderRadius: radius.md,
      padding: spacing.sm + 2,
      color: colors.text,
      ...typography.body,
    },
    composerActions: { flexDirection: "row", alignItems: "center", gap: spacing.md },
    photoButton: {
      flexDirection: "row",
      alignItems: "center",
      gap: spacing.xs,
      minHeight: 48,
      paddingHorizontal: spacing.md,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.borderStrong,
      backgroundColor: colors.surface,
    },
    photoButtonPressed: { backgroundColor: colors.surfaceAlt },
    photoButtonDisabled: { opacity: 0.4 },
    photoButtonText: { ...typography.subtitle, color: colors.text },
    errorText: { ...typography.body, color: colors.error, textAlign: "center" },
    centered: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.sm },
    list: { padding: spacing.lg, gap: spacing.sm },
    itemRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: spacing.sm,
      backgroundColor: colors.surface,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: colors.border,
      padding: spacing.md,
    },
    itemIcon: {
      width: 40,
      height: 40,
      borderRadius: radius.sm,
      backgroundColor: colors.surfaceAlt,
      borderWidth: 1,
      borderColor: colors.border,
      alignItems: "center",
      justifyContent: "center",
    },
    itemBody: { flex: 1, gap: 2 },
    itemCaption: { ...typography.body, color: colors.text },
    itemMeta: { ...typography.caption, color: colors.textFaint },
    deletePressed: { opacity: 0.6 },
  });
