/**
 * Tiny decoupling seam between the API client (src/api/client.ts, plain
 * functions with no React dependency) and the auth state machine
 * (src/auth/AuthContext.tsx, a React context). The client can't import
 * the context directly without becoming React-only, and the context
 * shouldn't import the client's internals — so a 401 on an authenticated
 * request is reported through this one-callback seam instead.
 */

type UnauthorizedHandler = () => void;

let handler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(next: UnauthorizedHandler | null): void {
  handler = next;
}

export function notifyUnauthorized(): void {
  handler?.();
}
