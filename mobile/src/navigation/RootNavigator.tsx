import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";

import { useAuth } from "../auth/AuthContext";
import { LoadingView } from "../components/LoadingView";
import { OnboardingNavigator } from "./OnboardingNavigator";
import { ExploreScreen } from "../screens/ExploreScreen";
import { HomeScreen } from "../screens/HomeScreen";
import { PoiDetailScreen } from "../screens/PoiDetailScreen";
import { SignInScreen } from "../screens/SignInScreen";
import { colors } from "../theme/tokens";
import { StyleSheet, View } from "react-native";

/**
 * Navigation foundation (MOBILE_ARCHITECTURE.md §2).
 *
 * Root branches on real auth AND onboarding state:
 *   - not authenticated              -> SignInScreen
 *   - authenticated, onboarding      -> OnboardingNavigator (shown once,
 *     status still unknown/incomplete   per FR-003, right after first sign-in)
 *   - authenticated, onboarding done -> Home / Explore / PoiDetail
 *     (MainTabNavigator's Phase-3+ stand-in — the full tab structure needs
 *     trip/AI features this project hasn't built yet, CLAUDE.md §12).
 *     Explore/PoiDetail are F6 (Maps & Navigation, Phase 5) — placed here
 *     rather than nested under a not-yet-built TripDetailStack because
 *     MOBILE_ARCHITECTURE.md's documented host screens for the map
 *     (ItineraryViewScreen, OnTripCompanionScreen) don't exist yet; see
 *     docs/PHASE_STATUS.md's Phase 5 section for this documented decision.
 */
export type RootStackParamList = {
  SignIn: undefined;
  Onboarding: undefined;
  Home: undefined;
  Explore: undefined;
  PoiDetail: { poiId: string };
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export function RootNavigator(): React.JSX.Element {
  const { state, onboardingCompleted } = useAuth();

  const stillCheckingOnboarding = state === "AUTHENTICATED" && onboardingCompleted === null;

  if (state === "AUTHENTICATING" || stillCheckingOnboarding) {
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
          onboardingCompleted ? (
            <>
              <Stack.Screen name="Home" component={HomeScreen} />
              <Stack.Screen name="Explore" component={ExploreScreen} />
              <Stack.Screen name="PoiDetail" component={PoiDetailScreen} />
            </>
          ) : (
            <Stack.Screen name="Onboarding" component={OnboardingNavigator} />
          )
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
