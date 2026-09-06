/**
 * Real, working app-wide UI-language system (Language Settings phase).
 *
 * Architecture, in order of preference per this phase's authorization
 * ("A. existing infra, B. local/static resources, C. existing AI
 * multilingual capability, D. external API only if truly required" — no
 * external translation API was introduced; see PHASE_STATUS.md):
 *
 *   - Fixed UI copy: local static resources (./locales/*.ts), a simple
 *     dot-path `t("namespace.key")` lookup — no new dependency.
 *   - AI-generated content (itinerary, chat, quick plan, heritage
 *     narration, photo Q&A): the SAME preferred_language value is sent to
 *     the backend (via the profile) and threaded into the Gemini prompt
 *     layer server-side (backend/app/services/ai/language.py) — this
 *     context is the single source of truth both UI copy and AI content
 *     read from.
 *   - Phrasebook / dynamic phrase translation: F10's existing
 *     Gemini-backed /v1/translate/* already handles arbitrary-language
 *     translation; unaffected by this phase, just now defaults to this
 *     same preference where a target language isn't explicitly chosen.
 *
 * Persistence: local-first (expo-secure-store, reusing the same storage
 * adapter as the Supabase session — see ../lib/secureStorage.ts — rather
 * than adding a new storage dependency) for an instant, offline-safe
 * apply with no network wait, PLUS best-effort sync to
 * `profiles.preferred_language` (PATCH /v1/auth/me) so the choice
 * survives reinstall / a new device / re-login, not just this install.
 *
 * Reconciliation rule (documented decision, CLAUDE.md §13 — the PRD/specs
 * don't say what should happen if local and server preferences ever
 * disagree, e.g. a fresh install after the account already set a language
 * on another device): if this device has never had an explicit local
 * choice, the server's value wins (so a new device inherits the account's
 * language). Once the user explicitly picks a language on THIS device,
 * that local choice wins from then on and is pushed to the server —
 * matching how most apps treat "this device's language setting" as
 * authoritative once set, while still bootstrapping sensibly for a fresh
 * install.
 *
 * First-run default: before any stored preference or server profile
 * exists (e.g. the SignIn screen itself, shown before authentication can
 * ever reach the backend), the OS device locale (`expo-localization`) is
 * used as a best-effort default when it matches a supported language —
 * never treated as an "explicit choice", so a genuine account preference
 * from another device still wins once sign-in completes.
 */

import * as Localization from "expo-localization";
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { updatePreferredLanguage } from "../api/auth";
import { ApiError } from "../api/client";
import { secureStorage } from "../lib/secureStorage";
import {
  DEFAULT_LANGUAGE,
  isSupportedLanguage,
  SUPPORTED_LANGUAGES,
  type LanguageCode,
} from "./languages";
import { en } from "./locales/en";
import { hi } from "./locales/hi";
import { kn } from "./locales/kn";
import { ml } from "./locales/ml";
import { ta } from "./locales/ta";
import { te } from "./locales/te";
import type { TranslationResources } from "./locales/en";

const STORAGE_KEY = "yatra_language";
const STORAGE_EXPLICIT_KEY = "yatra_language_explicit";

const OVERRIDES: Record<LanguageCode, object> = { en: {}, hi, te, ml, kn, ta };

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function deepMerge<T>(base: T, override: unknown): T {
  if (!isPlainObject(override)) return base;
  const result: Record<string, unknown> = { ...(base as Record<string, unknown>) };
  for (const key of Object.keys(override)) {
    const overrideValue = override[key];
    const baseValue = (base as Record<string, unknown>)[key];
    result[key] = isPlainObject(overrideValue)
      ? deepMerge(baseValue ?? {}, overrideValue)
      : overrideValue;
  }
  return result as T;
}

const RESOURCES: Record<LanguageCode, TranslationResources> = SUPPORTED_LANGUAGES.reduce(
  (acc, { code }) => {
    acc[code] = code === "en" ? en : deepMerge(en, OVERRIDES[code]);
    return acc;
  },
  {} as Record<LanguageCode, TranslationResources>,
);

function resolvePath(resource: unknown, path: string[]): unknown {
  let cursor: unknown = resource;
  for (const segment of path) {
    if (!isPlainObject(cursor)) return undefined;
    cursor = cursor[segment];
  }
  return cursor;
}

export interface LanguageContextValue {
  language: LanguageCode;
  ready: boolean;
  languageOptions: typeof SUPPORTED_LANGUAGES;
  /** Applies immediately (local storage), then best-effort syncs to the
   * backend profile. Returns whether the backend sync succeeded — callers
   * that want to surface a real error state (LanguageSettingsScreen) can
   * use this; the local UI change is never blocked or rolled back on a
   * sync failure, since local persistence + this session's requests are
   * already correct regardless. */
  setLanguage: (code: LanguageCode) => Promise<{ syncedToServer: boolean }>;
  /** Called once profile data is available (see HomeScreen's existing
   * profile-load effect) to reconcile local vs. server preference per the
   * rule documented above. */
  syncFromServerProfile: (serverLanguage: string | null | undefined) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const LanguageContext = createContext<LanguageContextValue | undefined>(undefined);

function detectDeviceLanguage(): LanguageCode {
  try {
    const deviceCode = Localization.getLocales()[0]?.languageCode;
    return isSupportedLanguage(deviceCode) ? deviceCode : DEFAULT_LANGUAGE;
  } catch {
    // expo-localization can throw in unusual host environments (e.g. some
    // web/test runners) — a locale guess is a nicety, never worth a crash.
    return DEFAULT_LANGUAGE;
  }
}

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return Object.entries(vars).reduce(
    (acc, [key, value]) => acc.replace(`{{${key}}}`, String(value)),
    template,
  );
}

export function LanguageProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  // Synchronous, so even the very first frame (SignInScreen, before any
  // storage read resolves) renders in a language the device is actually
  // set to, when supported, rather than always flashing English first.
  const [language, setLanguageState] = useState<LanguageCode>(detectDeviceLanguage);
  const [ready, setReady] = useState(false);
  const hasExplicitLocalChoice = useRef(false);
  const hasReconciledWithServer = useRef(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      secureStorage.getItem(STORAGE_KEY),
      secureStorage.getItem(STORAGE_EXPLICIT_KEY),
    ]).then(([storedLanguage, storedExplicit]) => {
      if (cancelled) return;
      if (isSupportedLanguage(storedLanguage)) {
        setLanguageState(storedLanguage);
      }
      hasExplicitLocalChoice.current = storedExplicit === "1";
      setReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const setLanguage = useCallback(
    async (code: LanguageCode): Promise<{ syncedToServer: boolean }> => {
      setLanguageState(code);
      hasExplicitLocalChoice.current = true;
      await secureStorage.setItem(STORAGE_KEY, code);
      await secureStorage.setItem(STORAGE_EXPLICIT_KEY, "1");

      try {
        await updatePreferredLanguage(code);
        return { syncedToServer: true };
      } catch (error) {
        // Best-effort: an unauthenticated caller (e.g. language picked
        // from a public screen) or a transient network failure never
        // blocks the local, immediately-applied change — only surfaced
        // back to the caller so a real error state can be shown where
        // that matters (LanguageSettingsScreen).
        if (error instanceof ApiError && error.status === 401) {
          return { syncedToServer: false };
        }
        return { syncedToServer: false };
      }
    },
    [],
  );

  const syncFromServerProfile = useCallback((serverLanguage: string | null | undefined): void => {
    if (hasReconciledWithServer.current || !isSupportedLanguage(serverLanguage)) return;
    hasReconciledWithServer.current = true;

    if (!hasExplicitLocalChoice.current) {
      // Fresh install / first sign-in on this device — adopt the
      // account's existing preference rather than silently staying on
      // the default.
      setLanguageState(serverLanguage);
      void secureStorage.setItem(STORAGE_KEY, serverLanguage);
      return;
    }

    if (serverLanguage !== language) {
      // This device already has an explicit choice that disagrees with
      // the account's stored value (e.g. it was set on another device) —
      // this device's explicit choice wins; push it so the account
      // converges to the most recently, explicitly chosen value.
      void updatePreferredLanguage(language).catch(() => {
        // Best-effort reconciliation; a failure here just means the
        // account-level value stays stale until the next successful
        // sync — never surfaced as an error since nothing the user did
        // just now actually failed.
      });
    }
  }, [language]);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>): string => {
      const path = key.split(".");
      const resource = RESOURCES[language] ?? en;
      const value = resolvePath(resource, path);
      if (typeof value === "string") return interpolate(value, vars);

      // Controlled fallback (CLAUDE.md: never broken/undefined text) —
      // English first, then the raw key as an absolute last resort so a
      // missing translation is visibly obvious in development rather
      // than silently blank.
      const fallback = resolvePath(en, path);
      return typeof fallback === "string" ? interpolate(fallback, vars) : key;
    },
    [language],
  );

  const value = useMemo<LanguageContextValue>(
    () => ({
      language,
      ready,
      languageOptions: SUPPORTED_LANGUAGES,
      setLanguage,
      syncFromServerProfile,
      t,
    }),
    [language, ready, setLanguage, syncFromServerProfile, t],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) {
    throw new Error("useLanguage() must be used within a LanguageProvider");
  }
  return ctx;
}

/** Alias matching the common `useTranslation()` naming convention — same
 * context, since this app has exactly one translation namespace source. */
export const useTranslation = useLanguage;
