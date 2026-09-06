import { act, renderHook } from "@testing-library/react-native";

import { useOnboardingStore } from "../onboardingStore";

describe("useOnboardingStore", () => {
  afterEach(async () => {
    // Must be an awaited async act(): a synchronous act() here leaves this
    // React 19 + test-renderer environment's internal act-tracking in a bad
    // state, which silently breaks the NEXT renderHook()/render() call in
    // this test file (mounts to a null/empty result, no error, no warning).
    // Every store mutation below is wrapped the same way for the same
    // reason.
    await act(async () => {
      useOnboardingStore.getState().reset();
    });
  });

  it("starts with no answers selected", async () => {
    const { result } = await renderHook(() => useOnboardingStore());

    expect(result.current.interestIds).toEqual([]);
    expect(result.current.travelStyle).toBeNull();
    expect(result.current.pace).toBeNull();
    expect(result.current.budgetBracket).toBeNull();
    expect(result.current.travelCompanion).toBeNull();
    expect(result.current.tripMotivation).toBe("");
  });

  it("toggleInterest adds an id, then removes it on a second toggle", async () => {
    const { result } = await renderHook(() => useOnboardingStore());

    await act(async () => result.current.toggleInterest(3));
    expect(result.current.interestIds).toEqual([3]);

    await act(async () => result.current.toggleInterest(7));
    expect(result.current.interestIds).toEqual([3, 7]);

    await act(async () => result.current.toggleInterest(3));
    expect(result.current.interestIds).toEqual([7]);
  });

  it("setTravelStyle / setPace / setBudgetBracket each overwrite the single selected value", async () => {
    const { result } = await renderHook(() => useOnboardingStore());

    await act(async () => result.current.setTravelStyle("planned"));
    expect(result.current.travelStyle).toBe("planned");
    await act(async () => result.current.setTravelStyle("spontaneous"));
    expect(result.current.travelStyle).toBe("spontaneous");

    await act(async () => result.current.setPace("packed"));
    expect(result.current.pace).toBe("packed");

    await act(async () => result.current.setBudgetBracket("premium"));
    expect(result.current.budgetBracket).toBe("premium");

    await act(async () => result.current.setTravelCompanion("solo"));
    expect(result.current.travelCompanion).toBe("solo");
    await act(async () => result.current.setTravelCompanion("family"));
    expect(result.current.travelCompanion).toBe("family");

    await act(async () => result.current.setTripMotivation("Trying local food"));
    expect(result.current.tripMotivation).toBe("Trying local food");
  });

  it("reset() clears every answer back to the initial empty state", async () => {
    const { result } = await renderHook(() => useOnboardingStore());

    await act(async () => {
      result.current.toggleInterest(1);
      result.current.setTravelStyle("flexible");
      result.current.setPace("relaxed");
      result.current.setBudgetBracket("budget");
      result.current.setTravelCompanion("couple");
      result.current.setTripMotivation("Slow mornings");
    });
    expect(result.current.interestIds).toEqual([1]);

    await act(async () => result.current.reset());

    expect(result.current.interestIds).toEqual([]);
    expect(result.current.travelStyle).toBeNull();
    expect(result.current.pace).toBeNull();
    expect(result.current.budgetBracket).toBeNull();
    expect(result.current.travelCompanion).toBeNull();
    expect(result.current.tripMotivation).toBe("");
  });
});
