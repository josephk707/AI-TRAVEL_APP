/**
 * Cross-platform storage adapter for @supabase/supabase-js's session
 * persistence.
 *
 * Native (iOS/Android): backed by expo-secure-store, which persists to
 * the platform Keychain (iOS) / Keystore-backed EncryptedSharedPreferences
 * (Android) — session tokens never touch plain AsyncStorage, a plaintext
 * file, or application source (MOBILE_ARCHITECTURE.md §1, CLAUDE.md §5).
 *
 * Web: expo-secure-store has no browser implementation — there is no OS
 * keychain for a browser tab to target. Supabase's own guidance for web
 * targets is to fall back to `localStorage`, which is what this does.
 * That fallback only matters for this phase's own explicitly-authorized
 * `expo start --web` validation path (docs/AUTHENTICATION_SETUP.md) — the
 * product itself ships as a native app, where the SecureStore path above
 * is what actually runs.
 */

import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

export interface KeyValueStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

const nativeStorage: KeyValueStorage = {
  getItem: (key) => SecureStore.getItemAsync(key),
  setItem: (key, value) => SecureStore.setItemAsync(key, value),
  removeItem: (key) => SecureStore.deleteItemAsync(key),
};

const webStorage: KeyValueStorage = {
  async getItem(key) {
    return typeof window === "undefined" ? null : window.localStorage.getItem(key);
  },
  async setItem(key, value) {
    if (typeof window !== "undefined") window.localStorage.setItem(key, value);
  },
  async removeItem(key) {
    if (typeof window !== "undefined") window.localStorage.removeItem(key);
  },
};

export const secureStorage: KeyValueStorage = Platform.OS === "web" ? webStorage : nativeStorage;
