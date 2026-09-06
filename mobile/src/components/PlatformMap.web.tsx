import React from "react";

/**
 * react-native-maps has no web support: its Fabric native-component spec
 * files (e.g. NativeComponentGooglePolygon.ts) call codegenNativeComponent,
 * which react-native-web does not implement — importing the real package
 * throws at *module-evaluation* time under Metro's web bundler, before
 * React ever renders, which crashes the whole page (a blank white screen
 * with no catchable React error). Metro resolves this file instead of
 * PlatformMap.tsx when bundling for web, so the real react-native-maps
 * import never reaches the web bundle at all.
 *
 * MapView/Marker throw on render (not on import) so the MapErrorBoundary
 * every screen already wraps them in (see ExploreScreen.tsx,
 * PoiDetailScreen.tsx) catches it via its existing, already-tested
 * componentDidCatch and falls back to the equivalent list view — reusing
 * the real error-recovery path rather than adding a new one.
 */
export function MapView(): React.ReactElement {
  throw new Error("Maps are not supported in the web preview build.");
}

export function Marker(): React.ReactElement {
  throw new Error("Maps are not supported in the web preview build.");
}

export const PROVIDER_GOOGLE = "google";
