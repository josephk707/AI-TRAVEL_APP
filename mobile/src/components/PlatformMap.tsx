/**
 * Native (iOS/Android) map primitives — a thin re-export of react-native-maps.
 * See PlatformMap.web.tsx for why this indirection exists at all: Metro
 * resolves that file instead of this one when bundling for web (standard
 * `.web.tsx` platform-extension resolution, already built into Expo/RN's
 * default Metro config — no metro.config.js change needed).
 */
export { default as MapView, Marker, PROVIDER_GOOGLE } from "react-native-maps";
