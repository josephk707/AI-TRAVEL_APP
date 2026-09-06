/**
 * Design-token foundation (MOBILE_ARCHITECTURE.md §10).
 *
 * Minimal monochrome theme phase — replaces the violet/indigo "Yatra AI"
 * palette with a restrained white-and-black system that ships BOTH a
 * light and a dark scheme. Colors are no longer a single static object:
 * every screen resolves the active palette at render time through
 * `useTheme()` / `useThemedStyles()` (see ./ThemeContext.tsx), so the
 * whole app follows the user's Appearance setting (System / Light / Dark).
 *
 * Design intent:
 *   - one accent only — black on white in light mode, white on black in
 *     dark mode — used for primary actions, active states and emphasis;
 *   - flat surfaces separated by hairline borders, not gradients, glows
 *     or heavy shadows;
 *   - strictly greyscale: even the semantic tokens (success / warning /
 *     error / gold) are greys — status meaning is carried by icon and
 *     label, the token only sets emphasis. No hue anywhere in the app.
 */

export type ColorScheme = "light" | "dark";

export interface ThemeColors {
  // Backgrounds & surfaces
  background: string;
  backgroundElevated: string;
  surface: string;
  surfaceAlt: string;
  surfaceHighlight: string;

  // Accent (monochrome: black in light mode, white in dark mode)
  primary: string;
  primaryStrong: string;
  primarySoft: string;
  primaryText: string;
  accent: string;
  gold: string;

  // Text
  text: string;
  textMuted: string;
  textFaint: string;

  // Structure
  border: string;
  borderStrong: string;
  divider: string;

  // Semantic
  success: string;
  successSoft: string;
  warning: string;
  warningSoft: string;
  error: string;
  errorSoft: string;
  info: string;

  overlay: string;
  white: string;
  black: string;
}

export const lightColors: ThemeColors = {
  background: "#FFFFFF",
  backgroundElevated: "#FFFFFF",
  surface: "#FFFFFF",
  surfaceAlt: "#F5F5F5",
  surfaceHighlight: "#EBEBEB",

  primary: "#111111",
  primaryStrong: "#000000",
  primarySoft: "#F2F2F2",
  primaryText: "#FFFFFF",
  accent: "#111111",
  gold: "#4A4A4A",

  text: "#111111",
  textMuted: "#6B6B6B",
  textFaint: "#9E9E9E",

  border: "#E6E6E6",
  borderStrong: "#CFCFCF",
  divider: "#EFEFEF",

  // Strictly greyscale: status is carried by icon + label, the color
  // only sets emphasis (error = strongest, warning = mid, success = calm).
  success: "#3A3A3A",
  successSoft: "#F2F2F2",
  warning: "#5C5C5C",
  warningSoft: "#F2F2F2",
  error: "#111111",
  errorSoft: "#EBEBEB",
  info: "#6B6B6B",

  overlay: "rgba(0, 0, 0, 0.45)",
  white: "#FFFFFF",
  black: "#000000",
};

export const darkColors: ThemeColors = {
  background: "#000000",
  backgroundElevated: "#0A0A0A",
  surface: "#111111",
  surfaceAlt: "#1A1A1A",
  surfaceHighlight: "#262626",

  primary: "#FFFFFF",
  primaryStrong: "#FFFFFF",
  primarySoft: "#1F1F1F",
  primaryText: "#000000",
  accent: "#FFFFFF",
  gold: "#BDBDBD",

  text: "#F5F5F5",
  textMuted: "#A3A3A3",
  textFaint: "#6E6E6E",

  border: "#262626",
  borderStrong: "#3A3A3A",
  divider: "#1F1F1F",

  success: "#CFCFCF",
  successSoft: "#1A1A1A",
  warning: "#B0B0B0",
  warningSoft: "#1A1A1A",
  error: "#F5F5F5",
  errorSoft: "#262626",
  info: "#9E9E9E",

  overlay: "rgba(0, 0, 0, 0.7)",
  white: "#FFFFFF",
  black: "#000000",
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

/** Tighter corners than the previous pill-heavy design — cards and
 * buttons read as crisp rectangles; `pill` is reserved for chips, badges
 * and circular icon buttons. */
export const radius = {
  sm: 6,
  md: 10,
  lg: 14,
  xl: 20,
  pill: 999,
} as const;

export const typography = {
  display: { fontSize: 32, fontWeight: "700" as const, letterSpacing: -0.6 },
  title: { fontSize: 26, fontWeight: "700" as const, letterSpacing: -0.4 },
  h1: { fontSize: 22, fontWeight: "700" as const, letterSpacing: -0.3 },
  h2: { fontSize: 18, fontWeight: "600" as const, letterSpacing: -0.2 },
  subtitle: { fontSize: 16, fontWeight: "600" as const },
  body: { fontSize: 15, fontWeight: "400" as const },
  bodyMedium: { fontSize: 15, fontWeight: "500" as const },
  caption: { fontSize: 13, fontWeight: "400" as const },
  captionMedium: { fontSize: 13, fontWeight: "600" as const },
  micro: { fontSize: 11, fontWeight: "600" as const, letterSpacing: 0.4 },
};

/** Elevation is almost entirely expressed through borders in this
 * design. Light mode keeps a barely-there card shadow so white cards
 * still separate from a white page on real hardware; dark mode uses none
 * (a black shadow on a black page is invisible — the border does the
 * work). */
export interface ThemeShadow {
  card: {
    shadowColor: string;
    shadowOffset: { width: number; height: number };
    shadowOpacity: number;
    shadowRadius: number;
    elevation: number;
  };
}

const lightShadow: ThemeShadow = {
  card: {
    shadowColor: "#000000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 1,
  },
};

const darkShadow: ThemeShadow = {
  card: {
    shadowColor: "#000000",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0,
    shadowRadius: 0,
    elevation: 0,
  },
};

export interface Theme {
  scheme: ColorScheme;
  isDark: boolean;
  colors: ThemeColors;
  shadow: ThemeShadow;
}

/** The two concrete themes. Module-level constants so their identity is
 * stable — `useThemedStyles()` memoizes on the theme object. */
export const themes: Record<ColorScheme, Theme> = {
  light: { scheme: "light", isDark: false, colors: lightColors, shadow: lightShadow },
  dark: { scheme: "dark", isDark: true, colors: darkColors, shadow: darkShadow },
};
