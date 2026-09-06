/**
 * Shared option lists for the onboarding wizard's single-select questions.
 *
 * Values here MUST stay in sync with backend/app/schemas/onboarding.py's
 * TravelStyle/Pace/BudgetBracket Literal types — see that module's
 * docstring for the documented resolution of the (otherwise ambiguous)
 * `travel_style` value set.
 */

import type { Ionicons } from "@expo/vector-icons";

export type TravelStyle = "planned" | "flexible" | "spontaneous";
export type Pace = "relaxed" | "balanced" | "packed";
export type BudgetBracket = "budget" | "mid" | "premium";
export type TravelCompanion = "solo" | "family" | "friends" | "couple" | "flexible";

type IconName = React.ComponentProps<typeof Ionicons>["name"];

export interface SelectOption<T extends string> {
  value: T;
  label: string;
  description: string;
  icon: IconName;
}

export const TRAVEL_STYLE_OPTIONS: SelectOption<TravelStyle>[] = [
  {
    value: "planned",
    label: "Planned",
    description: "I like a clear day-by-day itinerary before I go.",
    icon: "list-outline",
  },
  {
    value: "flexible",
    label: "Flexible",
    description: "A loose plan with room to change my mind.",
    icon: "shuffle-outline",
  },
  {
    value: "spontaneous",
    label: "Spontaneous",
    description: "Just the highlights — I'll figure out the rest there.",
    icon: "sparkles-outline",
  },
];

export const PACE_OPTIONS: SelectOption<Pace>[] = [
  {
    value: "relaxed",
    label: "Relaxed",
    description: "A stop or two a day, with plenty of downtime.",
    icon: "cafe-outline",
  },
  {
    value: "balanced",
    label: "Balanced",
    description: "A good mix of activity and rest.",
    icon: "walk-outline",
  },
  {
    value: "packed",
    label: "Packed",
    description: "See as much as possible, every day.",
    icon: "flash-outline",
  },
];

export const BUDGET_BRACKET_OPTIONS: SelectOption<BudgetBracket>[] = [
  {
    value: "budget",
    label: "Budget",
    description: "Keep costs low — hostels, street food, public transport.",
    icon: "wallet-outline",
  },
  {
    value: "mid",
    label: "Mid-range",
    description: "A comfortable balance of cost and comfort.",
    icon: "card-outline",
  },
  {
    value: "premium",
    label: "Premium",
    description: "Comfort and convenience matter more than saving.",
    icon: "diamond-outline",
  },
];

export const COMPANION_OPTIONS: SelectOption<TravelCompanion>[] = [
  {
    value: "solo",
    label: "Solo",
    description: "Just me, at my own pace.",
    icon: "person-outline",
  },
  {
    value: "family",
    label: "Family",
    description: "Travelling with parents, kids, or relatives.",
    icon: "people-outline",
  },
  {
    value: "friends",
    label: "Friends",
    description: "A group trip with friends.",
    icon: "people-circle-outline",
  },
  {
    value: "couple",
    label: "Couple",
    description: "Travelling with a partner.",
    icon: "heart-outline",
  },
  {
    value: "flexible",
    label: "Depends on the trip",
    description: "It varies — no fixed pattern.",
    icon: "shuffle-outline",
  },
];
