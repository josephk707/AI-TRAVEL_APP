/**
 * Environment configuration foundation.
 *
 * Expo exposes build-time env vars prefixed EXPO_PUBLIC_ to client code
 * (anything else stays server/CI-only and never reaches the bundle — see
 * docs/DEPLOYMENT_PLAN.md §4). Phase 3 adds the Supabase project
 * coordinates — the anon key is designed by Supabase to be public
 * (RLS is the real access boundary, not secrecy of this key); the
 * mobile app must never hold the service_role key, database password,
 * or JWT signing secret (CLAUDE.md §4).
 *
 * IMPORTANT: Metro's env-var inlining only recognizes STATIC
 * `process.env.EXPO_PUBLIC_X` member expressions — a dynamic
 * `process.env[name]` lookup is never replaced at build time and would
 * silently be `undefined` in a real device build even though it works in
 * the Metro dev server. Each variable is therefore read as its own
 * static expression (enforced by the `expo/no-dynamic-env-var` lint
 * rule), not via a generic helper.
 */

function withFallback(value: string | undefined, fallback: string): string {
  return value && value.trim().length > 0 ? value : fallback;
}

function required(value: string | undefined, name: string): string {
  if (!value || value.trim().length === 0) {
    // Fails loudly at module-load time rather than producing a client
    // that silently can't authenticate anyone — auth config is not
    // optional the way the API base URL's localhost fallback is.
    throw new Error(
      `Missing required environment variable ${name}. Copy mobile/.env.example to mobile/.env and fill it in.`,
    );
  }
  return value;
}

export const env = {
  apiBaseUrl: withFallback(process.env.EXPO_PUBLIC_API_BASE_URL, "http://localhost:8000"),
  supabaseUrl: required(process.env.EXPO_PUBLIC_SUPABASE_URL, "EXPO_PUBLIC_SUPABASE_URL"),
  supabaseAnonKey: required(
    process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY,
    "EXPO_PUBLIC_SUPABASE_ANON_KEY",
  ),
};
