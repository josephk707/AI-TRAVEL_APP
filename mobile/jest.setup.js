// Test-only fake values — never real credentials. Supabase config is
// required at module-load time in src/config/env.ts (a real app can't
// function without it), so unit tests need *something* here even though
// no test actually reaches a real Supabase project.
process.env.EXPO_PUBLIC_SUPABASE_URL ||= "https://test-project.supabase.co";
process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ||= "test-anon-key-not-a-real-secret";

// UI/UX Overhaul phase: expo-linear-gradient's real native view hangs
// `processColor` indefinitely under the Jest (non-native) environment,
// timing out every test that renders it (Button, IconBadge,
// BottomNavBar, GradientBackground all use it). A plain View stand-in is
// enough for component tests, which assert on text/testID content, not
// pixel output.
jest.mock("expo-linear-gradient", () => {
  const { View } = require("react-native");
  return { LinearGradient: View };
});
