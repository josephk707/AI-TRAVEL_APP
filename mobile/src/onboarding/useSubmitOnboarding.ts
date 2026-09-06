import { useCallback, useState } from "react";

import { submitOnboardingResponses } from "../api/onboarding";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { useOnboardingStore } from "./onboardingStore";

type SubmitState = "idle" | "submitting" | "error";

/**
 * Shared submit action for every onboarding screen's "Skip" link and for
 * OnboardingCompleteScreen's primary CTA — both submit whatever answers
 * are currently in the store (possibly none, for Skip) via ONE call to
 * POST /onboarding/responses.
 *
 * Per FR-003's exception flow, a save failure that the BACKEND itself
 * absorbs (still a 2xx/202 response, just `saved: false` while a
 * background retry runs) must not block the user — this hook treats that
 * the same as a full success and proceeds. Only a genuine request failure
 * (network error, 400 validation, 401, etc. — a thrown ApiError) surfaces
 * as this hook's `error` state, since that reflects something the user
 * can actually act on (e.g. retry).
 */
export function useSubmitOnboarding(): {
  submit: () => Promise<void>;
  state: SubmitState;
  errorMessage: string | null;
} {
  const { completeOnboardingLocally } = useAuth();
  const store = useOnboardingStore();
  const [state, setState] = useState<SubmitState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const submit = useCallback(async (): Promise<void> => {
    setState("submitting");
    setErrorMessage(null);
    try {
      await submitOnboardingResponses({
        interest_ids: store.interestIds,
        travel_style: store.travelStyle,
        pace: store.pace,
        budget_bracket: store.budgetBracket,
        travel_companion: store.travelCompanion,
        trip_motivation: store.tripMotivation.trim() || undefined,
      });
      store.reset();
      completeOnboardingLocally();
      setState("idle");
    } catch (cause) {
      setState("error");
      setErrorMessage(
        cause instanceof ApiError
          ? cause.message
          : "Could not save your answers. Please check your connection and try again.",
      );
    }
  }, [store, completeOnboardingLocally]);

  return { submit, state, errorMessage };
}
