import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";

import { useAuth } from "../auth/AuthContext";
import { LoadingView } from "../components/LoadingView";
import { OnboardingNavigator } from "./OnboardingNavigator";
import { BudgetViewScreen } from "../screens/BudgetViewScreen";
import { ChatScreen } from "../screens/ChatScreen";
import { CollectionsScreen } from "../screens/CollectionsScreen";
import { ExploreScreen } from "../screens/ExploreScreen";
import { HeritageNarrationScreen } from "../screens/HeritageNarrationScreen";
import { HomeScreen } from "../screens/HomeScreen";
import { ItineraryViewScreen } from "../screens/ItineraryViewScreen";
import { MemoryBoxScreen } from "../screens/MemoryBoxScreen";
import { NotificationsCentreScreen } from "../screens/NotificationsCentreScreen";
import { OnTripCompanionScreen } from "../screens/OnTripCompanionScreen";
import { PhotoQAScreen } from "../screens/PhotoQAScreen";
import { PhrasebookScreen } from "../screens/PhrasebookScreen";
import { PoiDetailScreen } from "../screens/PoiDetailScreen";
import { SignInScreen } from "../screens/SignInScreen";
import { TranslateScreen } from "../screens/TranslateScreen";
import { TripCreationScreen } from "../screens/TripCreationScreen";
import { TripsListScreen } from "../screens/TripsListScreen";
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
  TripsList: undefined;
  TripCreation: undefined;
  Chat: { tripId: string; interests?: string[]; useOwnIdeas?: boolean };
  ItineraryView: { tripId: string };
  Translate: undefined;
  HeritageNarration: { poiId: string; poiName: string };
  PhotoQA: { poiId: string; poiName: string };
  Collections: undefined;
  Notifications: undefined;
  BudgetView: { tripId: string };
  MemoryBox: { tripId: string };
  Phrasebook: { tripId: string };
  OnTripCompanion: { tripId: string };
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
              <Stack.Screen name="TripsList" component={TripsListScreen} />
              <Stack.Screen name="TripCreation" component={TripCreationScreen} />
              <Stack.Screen name="Chat" component={ChatScreen} />
              <Stack.Screen name="ItineraryView" component={ItineraryViewScreen} />
              <Stack.Screen name="Translate" component={TranslateScreen} />
              <Stack.Screen name="HeritageNarration" component={HeritageNarrationScreen} />
              <Stack.Screen name="PhotoQA" component={PhotoQAScreen} />
              <Stack.Screen name="Collections" component={CollectionsScreen} />
              <Stack.Screen name="Notifications" component={NotificationsCentreScreen} />
              <Stack.Screen name="BudgetView" component={BudgetViewScreen} />
              <Stack.Screen name="MemoryBox" component={MemoryBoxScreen} />
              <Stack.Screen name="Phrasebook" component={PhrasebookScreen} />
              <Stack.Screen name="OnTripCompanion" component={OnTripCompanionScreen} />
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
