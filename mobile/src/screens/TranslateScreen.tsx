import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from "expo-audio";
import React, { useCallback, useState } from "react";
import {
  ActivityIndicator,
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
import { translateSpeech, translateText, TranslateTextResult } from "../api/translation";
import { SelectableChip } from "../components/SelectableChip";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { colors, radius, spacing, typography } from "../theme/tokens";

/** F10 (dynamic extension) — the Local Phrase Assistant's arbitrary-phrase
 * translator (ARCHITECTURE_REVIEW.md M11), plus F25's speech-input half
 * (record -> transcribe -> translate; see translateSpeech's own docstring
 * for the real-time-vs-batch honesty boundary — this is not a live
 * duplex voice call). Real Gemini translation of whatever the traveller
 * types or says — never a lookup against a fixed phrase list. */
const LANGUAGES = ["Hindi", "Telugu", "Malayalam", "Kannada"];

type TranslateState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; result: TranslateTextResult; transcribedFrom?: string }
  | { status: "error"; message: string };

export function TranslateScreen(): React.JSX.Element {
  const [phrase, setPhrase] = useState("");
  const [language, setLanguage] = useState(LANGUAGES[0]);
  const [state, setState] = useState<TranslateState>({ status: "idle" });
  const [permissionError, setPermissionError] = useState<string | null>(null);

  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder);

  const handleTranslate = useCallback(async () => {
    const text = phrase.trim();
    if (!text) return;
    setState({ status: "loading" });
    try {
      const result = await translateText(text, language);
      setState({ status: "success", result });
    } catch (err) {
      setState({
        status: "error",
        message: err instanceof ApiError ? err.message : "Translation failed.",
      });
    }
  }, [phrase, language]);

  const startRecording = useCallback(async () => {
    setPermissionError(null);
    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) {
      setPermissionError("Microphone access is needed to speak a phrase.");
      return;
    }
    await recorder.prepareToRecordAsync();
    recorder.record();
  }, [recorder]);

  const stopRecordingAndTranslate = useCallback(async () => {
    await recorder.stop();
    const uri = recorder.uri;
    if (!uri) return;
    setState({ status: "loading" });
    try {
      const result = await translateSpeech(uri, language);
      setPhrase(result.transcribed_text);
      setState({
        status: "success",
        result: {
          original_text: result.transcribed_text,
          target_language: result.target_language,
          translated_text: result.translated_text,
          transliteration: result.transliteration,
          note: result.note,
          recognized_language: true,
        },
        transcribedFrom: result.transcribed_text,
      });
    } catch (err) {
      setState({
        status: "error",
        message: err instanceof ApiError ? err.message : "Speech translation failed.",
      });
    }
  }, [recorder, language]);

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <StatusBar style="dark" />
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.title}>Phrase translator</Text>
        <Text style={styles.subtitle}>
          Type or speak anything — Yatra AI translates it for the road, in script and in sound.
        </Text>

        <Text style={styles.label}>Translate to</Text>
        <View style={styles.chipRow}>
          {LANGUAGES.map((lang) => (
            <SelectableChip
              key={lang}
              label={lang}
              selected={language === lang}
              onPress={() => setLanguage(lang)}
              testID={`language-chip-${lang}`}
            />
          ))}
        </View>

        <Text style={styles.label}>Your phrase</Text>
        <TextInput
          style={[styles.input, styles.textarea]}
          placeholder="Where is the nearest railway station?"
          placeholderTextColor={colors.textMuted}
          value={phrase}
          onChangeText={setPhrase}
          multiline
          testID="translate-input"
        />

        <View style={styles.submitRow}>
          <Button
            label={state.status === "loading" ? "" : "Translate"}
            onPress={() => void handleTranslate()}
            disabled={!phrase.trim() || state.status === "loading"}
            testID="translate-button"
          />
          <Button
            label={recorderState.isRecording ? "⏹ Stop" : "🎤 Speak instead"}
            onPress={() =>
              void (recorderState.isRecording ? stopRecordingAndTranslate() : startRecording())
            }
            disabled={state.status === "loading"}
            testID="record-speech-button"
          />
          {state.status === "loading" && (
            <ActivityIndicator size="small" color={colors.primaryText} style={styles.spinner} />
          )}
        </View>

        {permissionError && (
          <Text style={styles.errorText} testID="record-permission-error">
            {permissionError}
          </Text>
        )}

        {state.status === "error" && (
          <Text style={styles.errorText} testID="translate-error">
            {state.message}
          </Text>
        )}

        {state.status === "success" && (
          <Card style={styles.resultCard} testID="translate-result">
            {state.transcribedFrom && (
              <Text style={styles.transcribedLabel}>Heard: &ldquo;{state.transcribedFrom}&rdquo;</Text>
            )}
            <Text style={styles.resultLanguage}>{state.result.target_language}</Text>
            <Text style={styles.resultText}>{state.result.translated_text}</Text>
            <Text style={styles.resultTransliteration}>{state.result.transliteration}</Text>
            {state.result.note && <Text style={styles.resultNote}>{state.result.note}</Text>}
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
  label: { ...typography.caption, color: colors.textMuted, marginTop: spacing.sm },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.sm + 2,
    color: colors.text,
    ...typography.body,
  },
  textarea: { minHeight: 80, textAlignVertical: "top" },
  submitRow: { marginTop: spacing.md, flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, alignItems: "center" },
  spinner: { marginLeft: spacing.sm },
  errorText: { ...typography.body, color: colors.error, marginTop: spacing.sm },
  resultCard: { marginTop: spacing.md, gap: spacing.xs },
  transcribedLabel: { ...typography.caption, color: colors.textMuted, fontStyle: "italic" },
  resultLanguage: { ...typography.caption, color: colors.textMuted, textTransform: "uppercase" },
  resultText: { ...typography.title, fontSize: 22, color: colors.text },
  resultTransliteration: { ...typography.body, color: colors.textMuted, fontStyle: "italic" },
  resultNote: { ...typography.caption, color: colors.warning, marginTop: spacing.xs },
});
