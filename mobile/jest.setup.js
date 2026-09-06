// Test-only fake values — never real credentials. Supabase config is
// required at module-load time in src/config/env.ts (a real app can't
// function without it), so unit tests need *something* here even though
// no test actually reaches a real Supabase project.
process.env.EXPO_PUBLIC_SUPABASE_URL ||= "https://test-project.supabase.co";
process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ||= "test-anon-key-not-a-real-secret";
