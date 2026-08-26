/**
 * Typed calls to /v1/translate/* — F10 dynamic (arbitrary-phrase) text
 * translation, ARCHITECTURE_REVIEW.md M11.
 */

import { apiPost, apiPostFormData } from "./client";

export interface TranslateTextResult {
  original_text: string;
  target_language: string;
  translated_text: string;
  transliteration: string;
  note: string | null;
  recognized_language: boolean;
}

interface Envelope<T> {
  data: T;
}

export async function translateText(
  text: string,
  targetLanguage: string,
): Promise<TranslateTextResult> {
  const envelope = await apiPost<Envelope<TranslateTextResult>>("/v1/translate/text", {
    text,
    target_language: targetLanguage,
  });
  return envelope.data;
}

export interface SpeechTranslateResult {
  transcribed_text: string;
  target_language: string;
  translated_text: string;
  transliteration: string;
  note: string | null;
}

/** F25 — batch speech translation: the client records a short clip and
 * uploads it whole; this is NOT a continuous real-time voice stream (see
 * backend/app/services/speech_translation_service.py's module docstring
 * for the documented capability boundary). */
export async function translateSpeech(
  audioUri: string,
  targetLanguage: string,
): Promise<SpeechTranslateResult> {
  const formData = new FormData();
  formData.append("target_language", targetLanguage);
  formData.append("audio", {
    uri: audioUri,
    name: "clip.m4a",
    type: "audio/mp4",
  } as unknown as Blob);

  const envelope = await apiPostFormData<Envelope<SpeechTranslateResult>>(
    "/v1/translate/speech",
    formData,
  );
  return envelope.data;
}
