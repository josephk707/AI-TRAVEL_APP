import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";

import { FoundationScreen } from "../screens/FoundationScreen";

/**
 * Navigation foundation (MOBILE_ARCHITECTURE.md §2).
 *
 * Phase 1 has exactly one route. The full RootNavigator ->
 * AuthStack/OnboardingStack/MainTabNavigator structure documented in
 * MOBILE_ARCHITECTURE.md is built out starting Phase 3 (Auth) once those
 * screens exist — standing up empty stacks now would be scaffolding
 * nothing (CLAUDE.md §12: prefer maintainability over unnecessary
 * complexity), so this establishes the *mechanism* (a typed native-stack
 * navigator inside a NavigationContainer) without pre-declaring routes
 * that don't exist yet.
 */
export type RootStackParamList = {
  Foundation: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator(): React.JSX.Element {
  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        <Stack.Screen name="Foundation" component={FoundationScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
