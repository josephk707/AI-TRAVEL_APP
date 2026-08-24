import React from "react";
import { StyleSheet, Text, View } from "react-native";

import { colors, spacing, typography } from "../theme/tokens";
import { Button } from "./Button";

interface Props {
  children: React.ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Root-level error boundary (CLAUDE.md §9 / §11: every screen must have an
 * error state, and a rendering crash anywhere below this boundary must
 * never white-screen the app). Catches render-time errors only (React
 * error boundaries cannot catch errors in async callbacks/event
 * handlers — those are handled per-call via try/catch, e.g. in
 * FoundationScreen's health check).
 */
export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // Phase 1 has no centralized error-reporting service yet
    // (DEPLOYMENT_PLAN.md §8, later phase) — console is the interim sink.
    console.error("ErrorBoundary caught a render error", error, info.componentStack);
  }

  private handleReset = (): void => {
    this.setState({ error: null });
  };

  render(): React.ReactNode {
    if (this.state.error) {
      return (
        <View style={styles.container} testID="error-boundary-fallback">
          <Text style={styles.title}>Something went wrong</Text>
          <Text style={styles.message}>{this.state.error.message}</Text>
          <Button label="Try again" onPress={this.handleReset} />
        </View>
      );
    }
    return this.props.children;
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.background,
    padding: spacing.lg,
    gap: spacing.md,
  },
  title: { ...typography.subtitle, color: colors.error },
  message: { ...typography.body, color: colors.textMuted, textAlign: "center" },
});
