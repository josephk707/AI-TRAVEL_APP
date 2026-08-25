import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";

import { useAuth } from "../auth/AuthContext";
import { LoadingView } from "../components/LoadingView";
import { HomeScreen } from "../screens/HomeScreen";
import { SignInScreen } from "../screens/SignInScreen";
import { colors } from "../theme/tokens";
import { StyleSheet, View } from "react-native";

/**
 * Navigation foundation (MOBILE_ARCHITECTURE.md §2).
 *
 * Phase 3 branches the root on real auth state: AuthStack (SignInScreen)
 * for anyone without a session, MainTabNavigator's Phase-3 stand-in
 * (HomeScreen) once one exists. The OnboardingStack and the full
 * MainTabNavigator tab structure aren't built yet — those require the
 * onboarding questionnaire and trip/AI features this phase explicitly
 * excludes — so authenticated users land on a single minimal screen
 * rather than empty scaffolding for routes that don't exist yet
 * (CLAUDE.md §12).
 */
export type RootStackParamList = {
  SignIn: undefined;
  Home: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator(): React.JSX.Element {
  const { state } = useAuth();

  if (state === "AUTHENTICATING") {
    return (
      <View style={styles.loadingContainer}>
        <LoadingView label="Loading…" />
      </View>
    );
  }

  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {state === "AUTHENTICATED" ? (
          <Stack.Screen name="Home" component={HomeScreen} />
        ) : (
          <Stack.Screen name="SignIn" component={SignInScreen} />
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  loadingContainer: { flex: 1, justifyContent: "center", backgroundColor: colors.background },
});
