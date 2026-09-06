import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from "expo-audio";
import * as Speech from "expo-speech";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

import { ApiError } from "../api/client";
import { translateSpeech, translateText, TranslateTextResult } from "../api/translation";
import { SelectableChip } from "../components/SelectableChip";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Screen } from "../components/Screen";
import { ScreenHeader } from "../components/ScreenHeader";
import { LanguageCode, SUPPORTED_LANGUAGES } from "../i18n/languages";
import { radius, spacing, type Theme, typography, useTheme, useThemedStyles } from "../theme";

/** F10 (dynamic extension) — the Local Phrase Assistant's arbitrary-phrase
 * translator (ARCHITECTURE_REVIEW.md M11), plus F25's speech-input half
 * (record -> transcribe -> translate; see translateSpeech's own docstring
 * for the real-time-vs-batch honesty boundary — this is not a live
 * duplex voice call).
 *
 * Final Personalization phase: aligned the language list to the app's own
 * i18n SUPPORTED_LANGUAGES (excluding English, the input language) instead
 * of a separately hand-maintained list — one language system, not two.
 * Also added a real 2-sentence input limit (matches
 * backend/app/schemas/translation.py's own validator exactly, so the UI
 * never lets a request reach the server only to be rejected) and voice
 * OUTPUT (expo-speech, real TTS of the real translated text — never a
 * pre-recorded clip). Voice INPUT gained a web-specific fallback: native
 * platforms keep the existing expo-audio record-upload-transcribe flow,
 * while web uses the browser's own SpeechRecognition API directly (no
 * server round trip needed — the browser already returns text), since
 * expo-audio's web recording support is not reliable in this project's
 * Expo SDK version.
 */
const TRANSLATE_LANGUAGES = SUPPORTED_LANGUAGES.filter((lang) => lang.code !== "en");

const MAX_SENTENCES = 2;
const MAX_CHARS = 500;
const SENTENCE_BOUNDARY = /[.!?]+(?:\s|$)/;

const TTS_LOCALES: Record<LanguageCode, string> = {
  en: "en-US",
  hi: "hi-IN",
  te: "te-IN",
  ml: "ml-IN",
  kn: "kn-IN",
  ta: "ta-IN",
};

function countSentences(text: string): number {
  const fragments = text
    .split(SENTENCE_BOUNDARY)
    .map((fragment) => fragment.trim())
    .filter((fragment) => fragment.length > 0);
  return Math.max(fragments.length, text.trim() ? 1 : 0);
}

// Minimal shape of the Web Speech API's SpeechRecognition — not part of
// React Native's TS lib, and only ever touched behind a Platform.OS ===
// "web" guard.
interface WebSpeechRecognitionEvent {
  results: { [index: number]: { [index: number]: { transcript: string } } };
}
interface WebSpeechRecognitionErrorEvent {
  error: string;
}
interface WebSpeechRecognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((event: WebSpeechRecognitionEvent) => void) | null;
  onerror: ((event: WebSpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
}

function getWebSpeechRecognitionCtor(): (new () => WebSpeechRecognition) | null {
  if (Platform.OS !== "web" || typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: new () => WebSpeechRecognition;
    webkitSpeechRecognition?: new () => WebSpeechRecognition;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

type TranslateState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; result: TranslateTextResult; transcribedFrom?: string }
  | { status: "error"; message: string };

export function TranslateScreen(): React.JSX.Element {
  const { colors, isDark } = useTheme();
  const styles = useThemedStyles(createStyles);
  const [phrase, setPhrase] = useState("");
  const [languageCode, setLanguageCode] = useState<LanguageCode>(TRANSLATE_LANGUAGES[0].code);
  const [state, setState] = useState<TranslateState>({ status: "idle" });
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [isWebListening, setIsWebListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const webRecognitionRef = useRef<WebSpeechRecognition | null>(null);

  const language = useMemo(
    () => TRANSLATE_LANGUAGES.find((lang) => lang.code === languageCode)?.englishLabel ?? "Hindi",
    [languageCode],
  );

  const sentenceCount = countSentences(phrase);
  const overLimit = sentenceCount > MAX_SENTENCES;

  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder);

  useEffect(() => {
    return () => {
      Speech.stop();
      webRecognitionRef.current?.stop();
    };
  }, []);

  const runTranslate = useCallback(
    async (text: string) => {
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
    },
    [language],
  );

  const handleTranslate = useCallback(async () => {
    const text = phrase.trim();
    if (!text) return;
    if (countSentences(text) > MAX_SENTENCES) {
      setState({
        status: "error",
        message: `This prototype translates at most ${MAX_SENTENCES} sentences at a time.`,
      });
      return;
    }
    await runTranslate(text);
  }, [phrase, runTranslate]);

  const startRecording = useCallback(async () => {
    setPermissionError(null);
    setState({ status: "idle" });
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

  const startWebListening = useCallback(() => {
    setPermissionError(null);
    setState({ status: "idle" });
    const Recognition = getWebSpeechRecognitionCtor();
    if (!Recognition) {
      setPermissionError("Voice input isn't supported in this browser.");
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "en-US";
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript?.trim();
      if (!transcript) {
        setState({ status: "error", message: "Couldn't hear a phrase. Please try again." });
        return;
      }
      setPhrase(transcript);
      void runTranslate(transcript);
    };
    recognition.onerror = (event) => {
      setIsWebListening(false);
      if (event.error === "not-allowed" || event.error === "permission-denied") {
        setPermissionError("Microphone access is needed to speak a phrase.");
      } else if (event.error === "no-speech") {
        setState({ status: "error", message: "No speech detected. Please try again." });
      } else if (event.error === "network") {
        setState({
          status: "error",
          message: "A network error interrupted voice recognition. Please try again.",
        });
      } else {
        setState({ status: "error", message: "Voice input failed. Please try again." });
      }
    };
    recognition.onend = () => setIsWebListening(false);

    webRecognitionRef.current = recognition;
    setIsWebListening(true);
    recognition.start();
  }, [runTranslate]);

  const stopWebListening = useCallback(() => {
    webRecognitionRef.current?.stop();
    setIsWebListening(false);
  }, []);

  const isRecording = Platform.OS === "web" ? isWebListening : recorderState.isRecording;

  const handleMicPress = useCallback(() => {
    if (Platform.OS === "web") {
      void (isWebListening ? stopWebListening() : startWebListening());
    } else {
      void (recorderState.isRecording ? stopRecordingAndTranslate() : startRecording());
    }
  }, [
    isWebListening,
    recorderState.isRecording,
    startRecording,
    startWebListening,
    stopRecordingAndTranslate,
    stopWebListening,
  ]);

  const handleListen = useCallback(() => {
    if (state.status !== "success") return;
    Speech.stop();
    setIsSpeaking(true);
    Speech.speak(state.result.translated_text, {
      language: TTS_LOCALES[languageCode],
      onDone: () => setIsSpeaking(false),
      onStopped: () => setIsSpeaking(false),
      onError: () => setIsSpeaking(false),
    });
  }, [state, languageCode]);

  return (
    <Screen>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
      <ScreenHeader title="Translate a phrase" subtitle="Up to two sentences at a time" />
      <ScrollView contentContainerStyle={styles.container}>
        <Text style={styles.label}>Your phrase (English)</Text>
        <TextInput
          style={[styles.input, styles.textarea]}
          placeholder="Where is the nearest railway station?"
          placeholderTextColor={colors.textFaint}
          keyboardAppearance={isDark ? "dark" : "light"}
          value={phrase}
          onChangeText={setPhrase}
          multiline
          maxLength={MAX_CHARS}
          testID="translate-input"
        />
        <Text
          style={[styles.sentenceCount, overLimit && styles.sentenceCountError]}
          testID="sentence-count"
        >
          {phrase.trim() ? sentenceCount : 0}/{MAX_SENTENCES} sentences
        </Text>

        <Text style={styles.label}>Translate to</Text>
        <View style={styles.chipRow}>
          {TRANSLATE_LANGUAGES.map((lang) => (
            <SelectableChip
              key={lang.code}
              label={lang.englishLabel}
              selected={languageCode === lang.code}
              onPress={() => setLanguageCode(lang.code)}
              testID={`language-chip-${lang.englishLabel}`}
            />
          ))}
        </View>

        <View style={styles.submitRow}>
          <Button
            label={state.status === "loading" ? "" : "Translate"}
            onPress={() => void handleTranslate()}
            disabled={!phrase.trim() || overLimit || state.status === "loading"}
            testID="translate-button"
            fullWidth={false}
          />
          <Button
            label={isRecording ? "⏹ Stop" : "🎤 Speak instead"}
            onPress={handleMicPress}
            disabled={state.status === "loading"}
            testID="record-speech-button"
            variant="secondary"
            fullWidth={false}
          />
          {state.status === "loading" && (
            <ActivityIndicator size="small" color={colors.text} style={styles.spinner} />
          )}
        </View>

        {isRecording && (
          <View style={styles.recordingRow} accessibilityLiveRegion="polite">
            <View style={styles.recordingDot} />
            <Text style={styles.recordingText}>Recording…</Text>
          </View>
        )}

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
            <Button
              label={isSpeaking ? "🔊 Speaking…" : "🔊 Listen"}
              onPress={handleListen}
              disabled={isSpeaking}
              testID="listen-button"
              variant="secondary"
              fullWidth={false}
            />
          </Card>
        )}
      </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const createStyles = ({ colors }: Theme) =>
  StyleSheet.create({
    flex: { flex: 1 },
    container: { padding: spacing.lg, paddingTop: 0, gap: spacing.sm },
    label: {
      ...typography.micro,
      color: colors.textMuted,
      textTransform: "uppercase",
      marginTop: spacing.sm,
    },
    chipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
    input: {
      borderWidth: 1,
      borderColor: colors.border,
      backgroundColor: colors.surface,
      borderRadius: radius.md,
      padding: spacing.sm + 4,
      color: colors.text,
      ...typography.body,
    },
    textarea: { minHeight: 96, textAlignVertical: "top" },
    sentenceCount: { ...typography.caption, color: colors.textFaint, textAlign: "right" },
    sentenceCountError: { color: colors.error },
    submitRow: {
      marginTop: spacing.md,
      flexDirection: "row",
      flexWrap: "wrap",
      gap: spacing.sm,
      alignItems: "center",
    },
    spinner: { marginLeft: spacing.sm },
    recordingRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: spacing.xs + 2,
      marginTop: spacing.xs,
    },
    recordingDot: {
      width: 8,
      height: 8,
      borderRadius: radius.pill,
      backgroundColor: colors.error,
    },
    recordingText: { ...typography.captionMedium, color: colors.error },
    errorText: { ...typography.body, color: colors.error, marginTop: spacing.sm },
    resultCard: { marginTop: spacing.md, gap: spacing.xs, alignItems: "flex-start" },
    transcribedLabel: { ...typography.caption, color: colors.textMuted, fontStyle: "italic" },
    resultLanguage: {
      ...typography.micro,
      color: colors.textMuted,
      textTransform: "uppercase",
    },
    resultText: { ...typography.title, fontSize: 22, color: colors.text },
    resultTransliteration: { ...typography.body, color: colors.textMuted, fontStyle: "italic" },
    resultNote: { ...typography.caption, color: colors.textMuted, marginTop: spacing.xs },
  });
