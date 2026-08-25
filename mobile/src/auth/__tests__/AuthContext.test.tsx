import type { Session } from "@supabase/supabase-js";
import { act, renderHook, waitFor } from "@testing-library/react-native";
import React from "react";

import { AuthProvider, useAuth } from "../AuthContext";

type AuthChangeCallback = (event: string, session: Session | null) => void;

const mockGetSession = jest.fn();
const mockOnAuthStateChange = jest.fn();
const mockSignInWithOAuth = jest.fn();
const mockExchangeCodeForSession = jest.fn();
const mockSignOut = jest.fn();

jest.mock("../../lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: (...args: unknown[]) => mockGetSession(...args),
      onAuthStateChange: (...args: unknown[]) => mockOnAuthStateChange(...args),
      signInWithOAuth: (...args: unknown[]) => mockSignInWithOAuth(...args),
      exchangeCodeForSession: (...args: unknown[]) => mockExchangeCodeForSession(...args),
      signOut: (...args: unknown[]) => mockSignOut(...args),
    },
  },
}));

const mockOpenAuthSessionAsync = jest.fn();
jest.mock("expo-web-browser", () => ({
  maybeCompleteAuthSession: jest.fn(),
  openAuthSessionAsync: (...args: unknown[]) => mockOpenAuthSessionAsync(...args),
}));

jest.mock("expo-linking", () => ({
  createURL: (path: string) => `aitouristguide://${path}`,
}));

const mockLogoutRequest = jest.fn();
jest.mock("../../api/auth", () => ({
  logout: (...args: unknown[]) => mockLogoutRequest(...args),
}));

function fakeSession(overrides: Partial<Session> = {}): Session {
  return {
    access_token: "fake-access-token",
    refresh_token: "fake-refresh-token",
    expires_in: 3600,
    token_type: "bearer",
    user: { id: "user-1", email: "traveller@example.com" },
    ...overrides,
  } as Session;
}

function wrapper({ children }: { children: React.ReactNode }): React.JSX.Element {
  return <AuthProvider>{children}</AuthProvider>;
}

let capturedListener: AuthChangeCallback | null = null;

beforeEach(() => {
  jest.clearAllMocks();
  capturedListener = null;
  mockOnAuthStateChange.mockImplementation((callback: AuthChangeCallback) => {
    capturedListener = callback;
    return { data: { subscription: { unsubscribe: jest.fn() } } };
  });
});

describe("AuthProvider / useAuth — state transitions", () => {
  it("settles on UNAUTHENTICATED when there is no session to restore", async () => {
    mockGetSession.mockResolvedValue({ data: { session: null }, error: null });

    const { result } = await renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.state).toBe("UNAUTHENTICATED"));
    expect(result.current.session).toBeNull();
  });

  it("settles on AUTHENTICATED when a session already exists (cold-start restoration)", async () => {
    const session = fakeSession();
    mockGetSession.mockResolvedValue({ data: { session }, error: null });

    const { result } = await renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.state).toBe("AUTHENTICATED"));
    expect(result.current.user?.id).toBe("user-1");
  });

  it("moves to AUTH_ERROR when session restoration itself fails", async () => {
    mockGetSession.mockResolvedValue({
      data: { session: null },
      error: { message: "network down" },
    });

    const { result } = await renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.state).toBe("AUTH_ERROR"));
    expect(result.current.errorMessage).toContain("sign in again");
  });

  it("moves to AUTHENTICATED when the SDK fires SIGNED_IN", async () => {
    mockGetSession.mockResolvedValue({ data: { session: null }, error: null });
    const { result } = await renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.state).toBe("UNAUTHENTICATED"));

    await act(() => {
      capturedListener?.("SIGNED_IN", fakeSession());
    });

    await waitFor(() => expect(result.current.state).toBe("AUTHENTICATED"));
  });

  it("distinguishes a deliberate signOut() (-> UNAUTHENTICATED) from an involuntary session loss (-> SESSION_EXPIRED)", async () => {
    mockGetSession.mockResolvedValue({ data: { session: fakeSession() }, error: null });
    mockSignOut.mockResolvedValue({ error: null });
    mockLogoutRequest.mockResolvedValue(undefined);
    const { result } = await renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.state).toBe("AUTHENTICATED"));

    // Case 1: the SDK fires SIGNED_OUT WITHOUT the app having called
    // signOut() itself — e.g. a refresh failure/revocation elsewhere.
    await act(() => {
      capturedListener?.("SIGNED_OUT", null);
    });
    await waitFor(() => expect(result.current.state).toBe("SESSION_EXPIRED"));

    // Restore to AUTHENTICATED, then exercise the deliberate path.
    await act(() => {
      capturedListener?.("SIGNED_IN", fakeSession());
    });
    await waitFor(() => expect(result.current.state).toBe("AUTHENTICATED"));

    await act(async () => {
      await result.current.signOut();
      capturedListener?.("SIGNED_OUT", null);
    });
    await waitFor(() => expect(result.current.state).toBe("UNAUTHENTICATED"));
    expect(mockLogoutRequest).toHaveBeenCalled();
  });

  it("signInWithGoogle(): happy path opens the auth session and exchanges the code", async () => {
    mockGetSession.mockResolvedValue({ data: { session: null }, error: null });
    mockSignInWithOAuth.mockResolvedValue({
      data: { url: "https://supabase.example/authorize" },
      error: null,
    });
    mockOpenAuthSessionAsync.mockResolvedValue({
      type: "success",
      url: "aitouristguide://auth/callback?code=abc123",
    });
    mockExchangeCodeForSession.mockResolvedValue({ error: null });

    const { result } = await renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.state).toBe("UNAUTHENTICATED"));

    await act(async () => {
      await result.current.signInWithGoogle();
    });

    expect(mockExchangeCodeForSession).toHaveBeenCalledWith("abc123");

    // The real SDK fires SIGNED_IN once the exchange completes internally
    // — simulate that here since exchangeCodeForSession is mocked.
    await act(() => {
      capturedListener?.("SIGNED_IN", fakeSession());
    });
    await waitFor(() => expect(result.current.state).toBe("AUTHENTICATED"));
  });

  it("signInWithGoogle(): user cancelling the consent screen returns to UNAUTHENTICATED, not an error", async () => {
    mockGetSession.mockResolvedValue({ data: { session: null }, error: null });
    mockSignInWithOAuth.mockResolvedValue({
      data: { url: "https://supabase.example/authorize" },
      error: null,
    });
    mockOpenAuthSessionAsync.mockResolvedValue({ type: "cancel" });

    const { result } = await renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.state).toBe("UNAUTHENTICATED"));

    await act(async () => {
      await result.current.signInWithGoogle();
    });

    expect(result.current.state).toBe("UNAUTHENTICATED");
    expect(mockExchangeCodeForSession).not.toHaveBeenCalled();
  });

  it("signInWithGoogle(): a provider-side failure lands on AUTH_ERROR with a message", async () => {
    mockGetSession.mockResolvedValue({ data: { session: null }, error: null });
    mockSignInWithOAuth.mockResolvedValue({
      data: { url: null },
      error: { message: "OAuth provider not configured" },
    });

    const { result } = await renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.state).toBe("UNAUTHENTICATED"));

    await act(async () => {
      await result.current.signInWithGoogle();
    });

    expect(result.current.state).toBe("AUTH_ERROR");
    expect(result.current.errorMessage).toBe("OAuth provider not configured");
  });

  it("clearError() returns from AUTH_ERROR to UNAUTHENTICATED and clears the message", async () => {
    mockGetSession.mockResolvedValue({
      data: { session: null },
      error: { message: "boom" },
    });

    const { result } = await renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.state).toBe("AUTH_ERROR"));

    await act(() => {
      result.current.clearError();
    });

    expect(result.current.state).toBe("UNAUTHENTICATED");
    expect(result.current.errorMessage).toBeNull();
  });
});
