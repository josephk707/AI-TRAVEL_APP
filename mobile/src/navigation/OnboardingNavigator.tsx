import React from "react";
import { createNativeStackNavigator } from "@react-navigation/native-stack";

import { BudgetBracketScreen } from "../screens/onboarding/BudgetBracketScreen";
import { InterestSelectScreen } from "../screens/onboarding/InterestSelectScreen";
import { OnboardingCompleteScreen } from "../screens/onboarding/OnboardingCompleteScreen";
import { TravelMotivationScreen } from "../screens/onboarding/TravelMotivationScreen";
import { TravelStyleScreen } from "../screens/onboarding/TravelStyleScreen";

/**
 * Onboarding flow (MOBILE_ARCHITECTURE.md §2's OnboardingStack) — shown
 * once, immediately after first sign-in, before the authenticated app.
 * 5 screens total (Final Personalization phase added TravelMotivation —
 * companion + open-ended question — as a 5th screen), still within the
 * ≤6-screen usability target (PRD Section 15 / FR-003 Business Rules).
 */
export type OnboardingStackParamList = {
  InterestSelect: undefined;
  TravelStyle: undefined;
  BudgetBracket: undefined;
  TravelMotivation: undefined;
  OnboardingComplete: undefined;
};

const Stack = createNativeStackNavigator<OnboardingStackParamList>();

export function OnboardingNavigator(): React.JSX.Element {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="InterestSelect" component={InterestSelectScreen} />
      <Stack.Screen name="TravelStyle" component={TravelStyleScreen} />
      <Stack.Screen name="BudgetBracket" component={BudgetBracketScreen} />
      <Stack.Screen name="TravelMotivation" component={TravelMotivationScreen} />
      <Stack.Screen name="OnboardingComplete" component={OnboardingCompleteScreen} />
    </Stack.Navigator>
  );
}
