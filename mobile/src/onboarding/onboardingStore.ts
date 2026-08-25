/**
 * Ephemeral, in-memory wizard state for the onboarding flow
 * (MOBILE_ARCHITECTURE.md §4: "Local UI state | Zustand | ... composer
 * draft text ... current tripUIMode override"). Answers are collected here
 * across InterestSelectScreen / TravelStyleScreen / BudgetBracketScreen,
 * then submitted in one POST /onboarding/responses call from
 * OnboardingCompleteScreen — never persisted to device storage, and reset
 * once the flow finishes (success or skip) so a later, separate onboarding
 * attempt (e.g. after a logout/login) never starts pre-filled with stale
 * answers.
 */

import { create } from "zustand";

import type { BudgetBracket, Pace, TravelStyle } from "./onboardingOptions";

interface OnboardingState {
  interestIds: number[];
  travelStyle: TravelStyle | null;
  pace: Pace | null;
  budgetBracket: BudgetBracket | null;
  toggleInterest: (id: number) => void;
  setTravelStyle: (value: TravelStyle) => void;
  setPace: (value: Pace) => void;
  setBudgetBracket: (value: BudgetBracket) => void;
  reset: () => void;
}

const initialAnswers = {
  interestIds: [] as number[],
  travelStyle: null as TravelStyle | null,
  pace: null as Pace | null,
  budgetBracket: null as BudgetBracket | null,
};

export const useOnboardingStore = create<OnboardingState>((set) => ({
  ...initialAnswers,
  toggleInterest: (id) =>
    set((state) => ({
      interestIds: state.interestIds.includes(id)
        ? state.interestIds.filter((existing) => existing !== id)
        : [...state.interestIds, id],
    })),
  setTravelStyle: (value) => set({ travelStyle: value }),
  setPace: (value) => set({ pace: value }),
  setBudgetBracket: (value) => set({ budgetBracket: value }),
  reset: () => set({ ...initialAnswers }),
}));
