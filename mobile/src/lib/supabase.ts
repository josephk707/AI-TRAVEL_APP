/**
 * The single Supabase client instance for the app (Auth client per
 * MOBILE_ARCHITECTURE.md §1). Every auth operation (OAuth sign-in,
 * session restoration, sign-out) goes through this instance — nothing
 * fabricates a session or a token locally.
 */

import { createClient } from "@supabase/supabase-js";

import { env } from "../config/env";
import { secureStorage } from "./secureStorage";

export const supabase = createClient(env.supabaseUrl, env.supabaseAnonKey, {
  auth: {
    storage: secureStorage,
    autoRefreshToken: true,
    persistSession: true,
    // We drive the OAuth redirect ourselves via expo-web-browser +
    // expo-linking (see src/auth/AuthContext.tsx) rather than letting the
    // client parse a browser URL — there is no ambient browser URL on
    // native.
    detectSessionInUrl: false,
    flowType: "pkce",
  },
});
