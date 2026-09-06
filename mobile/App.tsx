import React from "react";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { AuthProvider } from "./src/auth/AuthContext";
import { ErrorBoundary } from "./src/components/ErrorBoundary";
import { LanguageProvider } from "./src/i18n";
import { RootNavigator } from "./src/navigation/RootNavigator";
import { ThemedStatusBar, ThemeProvider } from "./src/theme";

export default function App(): React.JSX.Element {
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <ThemedStatusBar />
        <ErrorBoundary>
          <LanguageProvider>
            <AuthProvider>
              <RootNavigator />
            </AuthProvider>
          </LanguageProvider>
        </ErrorBoundary>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
