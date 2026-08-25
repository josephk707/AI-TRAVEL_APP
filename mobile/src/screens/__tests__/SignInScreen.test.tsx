import { fireEvent, render, screen } from "@testing-library/react-native";
import React from "react";

import { useAuth } from "../../auth/AuthContext";
import { SignInScreen } from "../SignInScreen";

jest.mock("../../auth/AuthContext", () => ({
  useAuth: jest.fn(),
}));

const mockUseAuth = useAuth as jest.Mock;

function authValue(overrides: Partial<ReturnType<typeof useAuth>> = {}) {
  return {
    state: "UNAUTHENTICATED" as const,
    session: null,
    user: null,
    errorMessage: null,
    signInWithGoogle: jest.fn(),
    signOut: jest.fn(),
    clearError: jest.fn(),
    ...overrides,
  };
}

describe("SignInScreen", () => {
  it("renders the Google sign-in button in the normal signed-out state", async () => {
    mockUseAuth.mockReturnValue(authValue());
    await render(<SignInScreen />);

    expect(screen.getByTestId("google-sign-in-button")).toBeTruthy();
    expect(screen.getByText("Continue with Google")).toBeTruthy();
    expect(screen.queryByTestId("session-expired-notice")).toBeNull();
    expect(screen.queryByTestId("auth-error-notice")).toBeNull();
  });

  it("calls signInWithGoogle() when the button is pressed", async () => {
    const signInWithGoogle = jest.fn();
    const clearError = jest.fn();
    mockUseAuth.mockReturnValue(authValue({ signInWithGoogle, clearError }));
    await render(<SignInScreen />);

    fireEvent.press(screen.getByTestId("google-sign-in-button"));

    expect(clearError).toHaveBeenCalled();
    expect(signInWithGoogle).toHaveBeenCalled();
  });

  it("shows a busy state and disables the button while AUTHENTICATING", async () => {
    mockUseAuth.mockReturnValue(authValue({ state: "AUTHENTICATING" }));
    await render(<SignInScreen />);

    expect(screen.getByText("Signing in…")).toBeTruthy();
  });

  it("shows the session-expired notice instead of the generic screen", async () => {
    mockUseAuth.mockReturnValue(authValue({ state: "SESSION_EXPIRED" }));
    await render(<SignInScreen />);

    expect(screen.getByTestId("session-expired-notice")).toBeTruthy();
  });

  it("shows the auth-error message when the last sign-in attempt failed", async () => {
    mockUseAuth.mockReturnValue(
      authValue({ state: "AUTH_ERROR", errorMessage: "Something went wrong" }),
    );
    await render(<SignInScreen />);

    expect(screen.getByTestId("auth-error-notice")).toBeTruthy();
    expect(screen.getByText("Something went wrong")).toBeTruthy();
  });
});
