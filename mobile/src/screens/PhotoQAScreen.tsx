import { useRoute } from "@react-navigation/native";
import type { RouteProp } from "@react-navigation/native";
import * as ImagePicker from "expo-image-picker";
import React, { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Image,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { StatusBar } from "expo-status-bar";

import { ApiError } from "../api/client";
import { askPhotoQuestion, PhotoQaResult } from "../api/heritage";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ConfidenceBadge } from "../components/ConfidenceBadge";
import type { RootStackParamList } from "../navigation/RootNavigator";
import { colors, radius, spacing, typography } from "../theme/tokens";

type AskState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; result: PhotoQaResult }
  | { status: "error"; message: string };

/** F9 — Photo-Based Landmark Q&A. Real multimodal Gemini call, grounded
 * against the same verified heritage content as F8 when available
 * (AI_ARCHITECTURE.md §6) — never a text-only placeholder. */
export function PhotoQAScreen(): React.JSX.Element {
  const route = useRoute<RouteProp<RootStackParamList, "PhotoQA">>();
  const { poiId, poiName } = route.params;

  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [state, setState] = useState<AskState>({ status: "idle" });

  const capturePhoto = useCallback(async () => {
    setPermissionError(null);
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) {
      setPermissionError("Camera access is needed to take a photo for this question.");
      return;
    }
    const result = await ImagePicker.launchCameraAsync({ quality: 0.7, base64: false });
    if (!result.canceled && result.assets?.[0]) {
      setPhotoUri(result.assets[0].uri);
      setState({ status: "idle" });
    }
  }, []);

  const pickFromLibrary = useCallback(async () => {
    setPermissionError(null);
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setPermissionError("Photo library access is needed to choose a photo.");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({ quality: 0.7 });
    if (!result.canceled && result.assets?.[0]) {
      setPhotoUri(result.assets[0].uri);
      setState({ status: "idle" });
    }
  }, []);

  const handleAsk = useCallback(async () => {
    if (!photoUri || !question.trim()) return;
    setState({ status: "loading" });
    try {
      const result = await askPhotoQuestion(poiId, question.trim(), photoUri);
      setState({ status: "success", result });
    } catch (err) {
      setState({
        status: "error",
        message: err instanceof ApiError ? err.message : "Couldn't answer that question.",
      });
    }
  }, [photoUri, question, poiId]);

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>Ask about a photo</Text>
        <Text style={styles.subtitle}>Near {poiName}</Text>

        {photoUri ? (
          <Image source={{ uri: photoUri }} style={styles.preview} testID="photo-preview" />
        ) : (
          <View style={styles.placeholder}>
            <Text style={styles.placeholderText}>No photo yet</Text>
          </View>
        )}

        <View style={styles.captureRow}>
          <Button label="Take photo" onPress={() => void capturePhoto()} testID="capture-photo-button" />
          <Button
            label="Choose from library"
            onPress={() => void pickFromLibrary()}
            testID="pick-photo-button"
          />
        </View>

        {permissionError && (
          <Text style={styles.errorText} testID="photo-permission-error">
            {permissionError}
          </Text>
        )}

        <Text style={styles.label}>Your question</Text>
        <TextInput
          style={styles.input}
          placeholder="What is this carving of?"
          placeholderTextColor={colors.textMuted}
          value={question}
          onChangeText={setQuestion}
          testID="photo-question-input"
        />

        <View style={styles.submitRow}>
          <Button
            label={state.status === "loading" ? "" : "Ask"}
            onPress={() => void handleAsk()}
            disabled={!photoUri || !question.trim() || state.status === "loading"}
            testID="ask-photo-question-button"
          />
          {state.status === "loading" && (
            <ActivityIndicator size="small" color={colors.primaryText} style={styles.spinner} />
          )}
        </View>

        {state.status === "error" && (
          <Text style={styles.errorText} testID="photo-qa-error">
            {state.message}
          </Text>
        )}

        {state.status === "success" && (
          <Card style={styles.resultCard} testID="photo-qa-result">
            <ConfidenceBadge confidence={state.result.confidence} testID="photo-qa-confidence" />
            <Text style={styles.resultText}>{state.result.answer}</Text>
          </Card>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  container: { padding: spacing.lg, gap: spacing.sm },
  title: { ...typography.title, color: colors.text },
  subtitle: { ...typography.body, color: colors.textMuted, marginBottom: spacing.sm },
  preview: { width: "100%", height: 220, borderRadius: radius.lg, backgroundColor: colors.surface },
  placeholder: {
    width: "100%",
    height: 220,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  placeholderText: { ...typography.body, color: colors.textMuted },
  captureRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  label: { ...typography.caption, color: colors.textMuted, marginTop: spacing.md },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.sm + 2,
    color: colors.text,
    ...typography.body,
  },
  submitRow: { marginTop: spacing.md, alignItems: "flex-start" },
  spinner: { position: "absolute", left: spacing.lg, top: spacing.sm + 2 },
  errorText: { ...typography.body, color: colors.error, marginTop: spacing.sm },
  resultCard: { marginTop: spacing.md, gap: spacing.sm },
  resultText: { ...typography.body, color: colors.text, lineHeight: 22 },
});
