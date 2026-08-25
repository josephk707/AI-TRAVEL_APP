/**
 * Centralized auth state (MOBILE_ARCHITECTURE.md §4's `useAuth()` context
 * wrapper). Five states, per this phase's spec:
 *
 *   AUTHENTICATING  — session restoration on cold start, or an OAuth
 *                      sign-in attempt is in flight
 *   AUTHENTICATED   — a real Supabase session exists
 *   UNAUTHENTICATED — no session; the normal signed-out state
 *   SESSION_EXPIRED — HAD a session that was lost involuntarily (refresh
 *                      failed / revoked elsewhere) — distinct from a
 *                      deliberate sign-out so the UI can say "please sign
 *                      in again" instead of the generic sign-in screen
 *   AUTH_ERROR      — the last sign-in attempt itself failed (network,
 *                      OAuth provider error, code exchange failure) —
 *                      recoverable by retrying, distinct from just being
 *                      signed out
 *
 * There is no client-fabricated session anywhere in this file: every
 * transition to AUTHENTICATED originates from a real
 * supabase.auth.* call (getSession, exchangeCodeForSession, or the
 * onAuthStateChange listener firing off one of those) — never a locally
 * constructed token.
 */

import type { Session, User } from "@supabase/supabase-js";
import * as Linking from "expo-linking";
import * as WebBrowser from "expo-web-browser";
import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";

import { logout as logoutRequest } from "../api/auth";
import { setUnauthorizedHandler } from "../api/authBridge";
import { supabase } from "../lib/supabase";

// Required once per app so an auth popup/browser tab closes itself after
// the redirect lands, on web and in the native in-app browser alike.
WebBrowser.maybeCompleteAuthSession();

export type AuthState =
  | "AUTHENTICATING"
  | "AUTHENTICATED"
  | "UNAUTHENTICATED"
  | "SESSION_EXPIRED"
  | "AUTH_ERROR";

interface AuthContextValue {
  state: AuthState;
  session: Session | null;
  user: User | null;
  errorMessage: string | null;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  /** Returns to UNAUTHENTICATED from AUTH_ERROR/SESSION_EXPIRED so the
   * sign-in screen can be retried without a stale error message lingering. */
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [state, setState] = useState<AuthState>("AUTHENTICATING");
  const [session, setSession] = useState<Session | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  // Distinguishes a deliberate signOut() call from an involuntary session
  // loss (refresh failure / revocation) — both surface as the SDK setting
  // session to null, but the correct end-state differs (UNAUTHENTICATED
  // vs SESSION_EXPIRED).
  const signOutInitiated = useRef(false);

  useEffect(() => {
    let cancelled = false;

    supabase.auth.getSession().then(({ data, error }) => {
      if (cancelled) return;
      if (error) {
        setState("AUTH_ERROR");
        setErrorMessage("Could not restore your session. Please sign in again.");
        return;
      }
      setSession(data.session);
      setState(data.session ? "AUTHENTICATED" : "UNAUTHENTICATED");
    });

    const { data: subscription } = supabase.auth.onAuthStateChange((event, nextSession) => {
      if (cancelled) return;

      setSession(nextSession);

      if (event === "SIGNED_IN" || event === "TOKEN_REFRESHED") {
        setErrorMessage(null);
        setState("AUTHENTICATED");
        return;
      }

      if (event === "SIGNED_OUT") {
        if (signOutInitiated.current) {
          signOutInitiated.current = false;
          setState("UNAUTHENTICATED");
        } else {
          setState("SESSION_EXPIRED");
        }
      }
    });

    // Bridges src/api/client.ts's 401 detection back into this state
    // machine: a request rejected by the backend even though the local
    // SDK still thought the token was valid means the session is no
    // longer good server-side (revoked/rotated) — force a real sign-out
    // (not the user-initiated path) so the listener above lands on
    // SESSION_EXPIRED, not UNAUTHENTICATED.
    setUnauthorizedHandler(() => {
      void supabase.auth.signOut();
    });

    return () => {
      cancelled = true;
      subscription.subscription.unsubscribe();
      setUnauthorizedHandler(null);
    };
  }, []);

  const signInWithGoogle = async (): Promise<void> => {
    setErrorMessage(null);
    setState("AUTHENTICATING");

    try {
      const redirectTo = Linking.createURL("auth/callback");
      const { data, error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo, skipBrowserRedirect: true },
      });

      if (error || !data.url) {
        setState("AUTH_ERROR");
        setErrorMessage(error?.message ?? "Could not start Google sign-in.");
        return;
      }

      const result = await WebBrowser.openAuthSessionAsync(data.url, redirectTo);

      if (result.type === "cancel" || result.type === "dismiss") {
        // The user backed out of the Google consent screen — not an
        // error, just a return to the normal signed-out state.
        setState("UNAUTHENTICATED");
        return;
      }

      if (result.type !== "success" || !result.url) {
        setState("AUTH_ERROR");
        setErrorMessage("Google sign-in did not complete.");
        return;
      }

      const code = new URL(result.url).searchParams.get("code");
      if (!code) {
        setState("AUTH_ERROR");
        setErrorMessage("Google sign-in did not return a valid authorization code.");
        return;
      }

      const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code);
      if (exchangeError) {
        setState("AUTH_ERROR");
        setErrorMessage(exchangeError.message);
        return;
      }
      // Success: onAuthStateChange's SIGNED_IN handler above sets
      // AUTHENTICATED once the SDK finishes processing the new session.
    } catch (cause) {
      setState("AUTH_ERROR");
      setErrorMessage(cause instanceof Error ? cause.message : "Sign-in failed unexpectedly.");
    }
  };

  const signOut = async (): Promise<void> => {
    signOutInitiated.current = true;

    try {
      // Real backend-mediated revoke (POST /v1/auth/logout) — proves the
      // full mobile -> FastAPI -> Supabase authenticated call chain for a
      // mutating request, not just the GET /auth/me read path.
      await logoutRequest();
    } catch {
      // Backend unreachable, or the token was already invalid — either
      // way this must never block clearing the LOCAL session below (see
      // app/services/auth_service.py's revoke_session for the matching
      // backend-side reasoning).
    }

    // scope: "local" — we already asked the backend to revoke the
    // session above; this just clears the on-device SecureStore copy
    // rather than making a second, now-redundant network call to GoTrue.
    const { error } = await supabase.auth.signOut({ scope: "local" });
    if (error) {
      // Sign-out itself failing is rare (this is a local-only operation
      // once scoped as above) — but if it does, don't strand the user in
      // a state claiming they're still authenticated.
      signOutInitiated.current = false;
      setState("UNAUTHENTICATED");
      setSession(null);
    }
  };

  const clearError = (): void => {
    setErrorMessage(null);
    setState("UNAUTHENTICATED");
  };

  const value = useMemo<AuthContextValue>(
    () => ({
      state,
      session,
      user: session?.user ?? null,
      errorMessage,
      signInWithGoogle,
      signOut,
      clearError,
    }),
    [state, session, errorMessage],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth() must be used within an AuthProvider");
  }
  return ctx;
}
