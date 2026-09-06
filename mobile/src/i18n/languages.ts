/**
 * Supported UI languages — Language Settings phase.
 *
 * Deliberately the union of what this codebase's OTHER two language
 * features already support, not a new product decision:
 *   - F10 dynamic text/speech translation (Hindi, Telugu, Malayalam, Kannada)
 *   - F10 phrasebook seed content (Hindi, Kannada, Tamil)
 * `code` matches `profiles.preferred_language`'s CHECK constraint
 * (supabase/migrations/20260828120002_add_preferred_language.sql) and
 * backend/app/schemas/auth.py's SupportedLanguage literal exactly.
 */

export type LanguageCode = "en" | "hi" | "te" | "ml" | "kn" | "ta";

export interface LanguageOption {
  code: LanguageCode;
  /** Shown to a reader of the CURRENTLY selected language (e.g. English UI shows "Hindi"). */
  englishLabel: string;
  /** Shown in the language's own script, so a user can find their language even if the
   * current UI language is one they can't read. */
  nativeLabel: string;
}

export const SUPPORTED_LANGUAGES: LanguageOption[] = [
  { code: "en", englishLabel: "English", nativeLabel: "English" },
  { code: "hi", englishLabel: "Hindi", nativeLabel: "हिन्दी" },
  { code: "te", englishLabel: "Telugu", nativeLabel: "తెలుగు" },
  { code: "ml", englishLabel: "Malayalam", nativeLabel: "മലയാളം" },
  { code: "kn", englishLabel: "Kannada", nativeLabel: "ಕನ್ನಡ" },
  { code: "ta", englishLabel: "Tamil", nativeLabel: "தமிழ்" },
];

export const DEFAULT_LANGUAGE: LanguageCode = "en";

export function isSupportedLanguage(value: string | null | undefined): value is LanguageCode {
  return !!value && SUPPORTED_LANGUAGES.some((l) => l.code === value);
}
