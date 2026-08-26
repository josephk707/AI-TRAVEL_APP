// Converted from the previous static app.json (Phase 5, F6) specifically
// to inject the Google Maps SDK key (tile-rendering only — a DIFFERENT
// key from the backend's server-side GOOGLE_MAPS_API_KEY, see
// MOBILE_ARCHITECTURE.md §8 and docs/PHASE_STATUS.md's Phase 5 section)
// into the native build config. Expo CLI loads .env files before
// evaluating this file, so EXPO_PUBLIC_-prefixed variables are already
// populated on process.env here, same as they are in the JS bundle.
// EXPO_PUBLIC_ is the right prefix even though this value ends up in
// native config rather than the JS bundle: like the Supabase anon key
// (mobile/.env.example), a Maps SDK key is designed to be embedded in a
// shipped client and is protected by platform/bundle-ID restriction in
// the Google Cloud Console, not by secrecy.
const googleMapsSdkKey = process.env.EXPO_PUBLIC_GOOGLE_MAPS_SDK_KEY || undefined;

/** @type {import('expo/config').ExpoConfig} */
module.exports = {
  expo: {
    name: "AI Tourist Guide",
    slug: "ai-tourist-guide",
    scheme: "aitouristguide",
    version: "0.1.0",
    orientation: "portrait",
    icon: "./assets/icon.png",
    userInterfaceStyle: "light",
    ios: {
      supportsTablet: true,
      config: googleMapsSdkKey ? { googleMapsApiKey: googleMapsSdkKey } : undefined,
    },
    android: {
      adaptiveIcon: {
        backgroundColor: "#E6F4FE",
        foregroundImage: "./assets/android-icon-foreground.png",
        backgroundImage: "./assets/android-icon-background.png",
        monochromeImage: "./assets/android-icon-monochrome.png",
      },
      predictiveBackGestureEnabled: false,
      config: googleMapsSdkKey ? { googleMaps: { apiKey: googleMapsSdkKey } } : undefined,
    },
    web: {
      favicon: "./assets/favicon.png",
    },
    plugins: [
      "expo-secure-store",
      "expo-web-browser",
      "expo-asset",
      "expo-audio",
      [
        "expo-location",
        {
          locationAlwaysAndWhenInUsePermission:
            "Yatra AI uses your location, once you enable it for a trip, to detect arrivals at planned stops and suggest what's nearby.",
        },
      ],
      "expo-notifications",
    ],
  },
};
