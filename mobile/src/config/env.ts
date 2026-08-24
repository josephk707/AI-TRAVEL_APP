/**
 * Environment configuration foundation.
 *
 * Expo exposes build-time env vars prefixed EXPO_PUBLIC_ to client code
 * (anything else stays server/CI-only and never reaches the bundle — see
 * docs/DEPLOYMENT_PLAN.md §4). Phase 1 only needs the API base URL; later
 * phases add the Supabase publishable coordinates here (never a secret
 * key — CLAUDE.md §4).
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

export const env = {
  apiBaseUrl: withFallback(process.env.EXPO_PUBLIC_API_BASE_URL, "http://localhost:8000"),
};
