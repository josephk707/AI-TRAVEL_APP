/**
 * App-wide appearance system (minimal monochrome theme phase).
 *
 *   - `ThemeProvider` owns the user's Appearance preference —
 *     "system" (follow the OS), "light" or "dark" — persisted locally via
 *     the same expo-secure-store adapter the language setting already
 *     uses (../lib/secureStorage.ts), so the choice survives restarts
 *     with no new storage dependency and no network round-trip.
 *   - `useTheme()` returns the resolved theme (colors, shadow, isDark…)
 *     plus the preference controls. It degrades gracefully when no
 *     provider is mounted (isolated component tests, the root
 *     ErrorBoundary fallback): it follows the OS scheme and exposes a
 *     no-op setter, so no consumer ever throws for lack of a provider.
 *   - `useThemedStyles(factory)` is the per-file replacement for a static
 *     `StyleSheet.create(...)`: pass a module-level factory
 *     `(theme) => StyleSheet.create({...})` and get back styles for the
 *     active scheme, memoized until the scheme changes.
 */

import { StatusBar } from "expo-status-bar";
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { type ColorSchemeName, useColorScheme } from "react-native";

import { secureStorage } from "../lib/secureStorage";
import { type ColorScheme, type Theme, themes } from "./tokens";

export type ThemeMode = "system" | "light" | "dark";

export const THEME_MODES: readonly ThemeMode[] = ["system", "light", "dark"];

const STORAGE_KEY = "yatra_theme_mode";

export function isThemeMode(value: unknown): value is ThemeMode {
  return typeof value === "string" && (THEME_MODES as readonly string[]).includes(value);
}

export interface ThemeContextValue extends Theme {
  /** The stored preference (what the user picked), as opposed to
   * `scheme`, which is what is actually being rendered right now. */
  mode: ThemeMode;
  /** False until the persisted preference has been read on launch. */
  ready: boolean;
  setMode: (mode: ThemeMode) => Promise<void>;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

function resolveScheme(mode: ThemeMode, systemScheme: ColorSchemeName): ColorScheme {
  if (mode === "system") return systemScheme === "dark" ? "dark" : "light";
  return mode;
}

export function ThemeProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const systemScheme = useColorScheme();
  const [mode, setModeState] = useState<ThemeMode>("system");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    secureStorage
      .getItem(STORAGE_KEY)
      .then((stored) => {
        if (cancelled) return;
        if (isThemeMode(stored)) setModeState(stored);
        setReady(true);
      })
      .catch((error: unknown) => {
        // A storage read failure must never block the app — fall back to
        // following the OS, but say so in the log rather than hiding it.
        console.warn("Theme preference could not be read; following system appearance", error);
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const setMode = useCallback(async (next: ThemeMode): Promise<void> => {
    setModeState(next);
    try {
      await secureStorage.setItem(STORAGE_KEY, next);
    } catch (error: unknown) {
      // The in-memory change already applied; only persistence failed.
      console.warn("Theme preference could not be persisted", error);
    }
  }, []);

  const scheme = resolveScheme(mode, systemScheme);

  const value = useMemo<ThemeContextValue>(
    () => ({ ...themes[scheme], mode, ready, setMode }),
    [scheme, mode, ready, setMode],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

const noopSetMode = async (): Promise<void> => {};

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  const systemScheme = useColorScheme();
  return useMemo<ThemeContextValue>(() => {
    if (ctx) return ctx;
    const scheme = resolveScheme("system", systemScheme);
    return { ...themes[scheme], mode: "system", ready: true, setMode: noopSetMode };
  }, [ctx, systemScheme]);
}

/**
 * Resolve a module-level style factory against the active theme.
 * The factory MUST be defined at module scope (stable identity) so the
 * memo only recomputes when the scheme actually changes.
 */
export function useThemedStyles<T>(factory: (theme: Theme) => T): T {
  const theme = useTheme();
  return useMemo(() => factory(theme), [factory, theme]);
}

/** Single status-bar owner for the whole app (rendered once in App.tsx)
 * — light icons on a dark page, dark icons on a white page. */
export function ThemedStatusBar(): React.JSX.Element {
  const { isDark } = useTheme();
  return <StatusBar style={isDark ? "light" : "dark"} />;
}
