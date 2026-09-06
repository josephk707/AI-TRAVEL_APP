/**
 * Design-token foundation (MOBILE_ARCHITECTURE.md §10).
 *
 * UI/UX Overhaul phase — replaces the Phase-1 minimal light token set with
 * the premium dark "Yatra AI" visual language (violet/indigo, glassy
 * cards, soft glows) matching the supplied design reference. Every
 * existing call site imports these same names (`colors`, `spacing`,
 * `radius`, `typography`) so this is a drop-in re-skin — no screen needs
 * to change its import shape, only what a handful of new tokens
 * (`gradients`, `shadow`, `radius.pill`, `typography.display/h1/h2`)
 * unlock for the redesigned screens.
 */

export const colors = {
  // Backgrounds — a deep indigo-violet base, not flat black, so gradients
  // and glow accents (see `gradients` below) have somewhere to bloom.
  background: "#0B0A18",
  backgroundElevated: "#131128",
  surface: "#1A1730",
  surfaceAlt: "#221E3F",
  surfaceHighlight: "#2A2450",

  // Brand
  primary: "#7C5CFC",
  primaryStrong: "#6339F5",
  primarySoft: "rgba(124, 92, 252, 0.16)",
  primaryText: "#FFFFFF",
  accent: "#C084FC",
  gold: "#F5B94D",

  // Text
  text: "#F4F2FF",
  textMuted: "#A79FC7",
  textFaint: "#6F6892",

  // Structure
  border: "rgba(255, 255, 255, 0.09)",
  borderStrong: "rgba(255, 255, 255, 0.16)",
  divider: "rgba(255, 255, 255, 0.06)",

  // Semantic
  success: "#34D399",
  successSoft: "rgba(52, 211, 153, 0.16)",
  warning: "#F5B94D",
  warningSoft: "rgba(245, 185, 77, 0.16)",
  error: "#F87171",
  errorSoft: "rgba(248, 113, 113, 0.16)",
  info: "#60A5FA",

  overlay: "rgba(6, 5, 16, 0.72)",
  white: "#FFFFFF",
} as const;

/** Linear-gradient color stops (`expo-linear-gradient`), reused across
 * hero backgrounds, primary buttons, and highlighted cards so the whole
 * app shares the same few gradients instead of screens inventing their
 * own. Angle/direction is chosen per usage site via `start`/`end`. */
export const gradients = {
  primaryButton: ["#8B5CF6", "#6339F5"] as const,
  hero: ["#2C2559", "#151030", "#0B0A18"] as const,
  card: ["#242046", "#191531"] as const,
  glow: ["rgba(124, 92, 252, 0.35)", "rgba(124, 92, 252, 0)"] as const,
  gold: ["#F9D67A", "#F0A93E"] as const,
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

export const radius = {
  sm: 8,
  md: 14,
  lg: 20,
  xl: 28,
  pill: 999,
} as const;

export const typography = {
  display: { fontSize: 32, fontWeight: "700" as const, letterSpacing: -0.5 },
  title: { fontSize: 26, fontWeight: "700" as const, letterSpacing: -0.3 },
  h1: { fontSize: 22, fontWeight: "700" as const, letterSpacing: -0.2 },
  h2: { fontSize: 18, fontWeight: "600" as const },
  subtitle: { fontSize: 16, fontWeight: "600" as const },
  body: { fontSize: 15, fontWeight: "400" as const },
  bodyMedium: { fontSize: 15, fontWeight: "500" as const },
  caption: { fontSize: 13, fontWeight: "400" as const },
  captionMedium: { fontSize: 13, fontWeight: "600" as const },
  micro: { fontSize: 11, fontWeight: "600" as const, letterSpacing: 0.4 },
};

/** react-native `shadow*` + Android `elevation`, tuned for dark
 * surfaces (a pure-black shadow reads as "nothing" on a dark background —
 * these use the brand violet at low opacity so elevated cards actually
 * separate from the base). */
export const shadow = {
  card: {
    shadowColor: "#000000",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.35,
    shadowRadius: 16,
    elevation: 6,
  },
  glow: {
    shadowColor: colors.primary,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.45,
    shadowRadius: 18,
    elevation: 8,
  },
} as const;
