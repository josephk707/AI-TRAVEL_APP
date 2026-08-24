/**
 * Design-token foundation (MOBILE_ARCHITECTURE.md §10).
 *
 * A minimal token set for Phase 1 — colors, spacing, typography, radius.
 * Real destination-imagery/premium-feel polish (CLAUDE.md §11) is layered
 * on top of this foundation once real screens exist; Phase 1 only needs
 * the tokens to exist and be consistently used, not the full visual
 * language.
 */

export const colors = {
  background: "#FFFFFF",
  surface: "#F7F5F2",
  primary: "#0F6E5B",
  primaryText: "#FFFFFF",
  text: "#1B1B1F",
  textMuted: "#6B6B72",
  border: "#E4E1DB",
  success: "#1E8E5A",
  error: "#C0392B",
  warning: "#B8860B",
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
} as const;

export const radius = {
  sm: 6,
  md: 12,
  lg: 20,
} as const;

export const typography = {
  title: { fontSize: 28, fontWeight: "700" as const },
  subtitle: { fontSize: 17, fontWeight: "500" as const },
  body: { fontSize: 15, fontWeight: "400" as const },
  caption: { fontSize: 13, fontWeight: "400" as const },
};
