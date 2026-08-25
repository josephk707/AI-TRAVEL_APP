import React from "react";

interface Props {
  /** Rendered normally. */
  children: React.ReactNode;
  /** Rendered instead of `children` once a render error is caught — the
   * list view of the same results, per MOBILE_ARCHITECTURE.md §8's
   * documented "map-tile load failure → automatic fallback to a list
   * view" behavior (F6). */
  fallback: React.ReactNode;
}

interface State {
  hasError: boolean;
}

/**
 * A narrow, map-specific error boundary — deliberately separate from the
 * app-wide `ErrorBoundary` (whose fallback is a generic "Something went
 * wrong / Try again" screen, not appropriate here): this one swaps
 * straight to the equivalent list view with no user action required,
 * since the underlying data is still perfectly usable without the map.
 *
 * React error boundaries only catch render-time errors, not native-level
 * tile rendering failures (e.g. a missing/invalid Maps SDK key, which
 * fails silently at the native layer rather than throwing a JS
 * exception) — this boundary covers the JS-render failure class
 * (a malformed region/marker prop, an unexpected native-module absence in
 * an environment that doesn't have it installed, etc.), which is the
 * portion of "map can fail" that is actually testable and catchable from
 * JavaScript. See docs/PHASE_STATUS.md's Phase 5 Known Limitations for
 * the native-tile-failure gap, which has no JS-visible signal to catch.
 */
export class MapErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error("Map failed to render, falling back to list view", error, info.componentStack);
  }

  render(): React.ReactNode {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}
