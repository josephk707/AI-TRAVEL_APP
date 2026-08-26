/**
 * API client foundation (MOBILE_ARCHITECTURE.md §9).
 *
 * A thin, typed fetch wrapper. Phase 3 adds authenticated requests: every
 * call reads the CURRENT Supabase session fresh (via supabase.auth.
 * getSession(), which itself awaits any in-flight token refresh) rather
 * than caching a token — there is no window where a stale, already-
 * refreshed-away token gets sent. No generated OpenAPI client yet (no
 * versioned product API surface exists to generate from beyond auth —
 * Phase 4+).
 */

import { env } from "../config/env";
import { notifyUnauthorized } from "./authBridge";
import { supabase } from "../lib/supabase";

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly details?: unknown;

  constructor(status: number, message: string, code?: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface ErrorEnvelope {
  error: { code: string; message: string; details?: unknown };
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as { error: unknown }).error === "object"
  );
}

async function authHeader(): Promise<Record<string, string>> {
  // Never logged — this function's return value must never appear in a
  // console.log/error call anywhere in the app (CLAUDE.md §4).
  const { data } = await supabase.auth.getSession();
  return data.session ? { Authorization: `Bearer ${data.session.access_token}` } : {};
}

async function request<T>(
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  options: { signal?: AbortSignal; body?: unknown } = {},
): Promise<T> {
  const url = `${env.apiBaseUrl}${path}`;
  const auth = await authHeader();
  let response: Response;

  try {
    response = await fetch(url, {
      method,
      headers: {
        Accept: "application/json",
        ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...auth,
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  } catch (cause) {
    // Network-level failure (no connectivity, DNS, backend down) —
    // never swallowed, always surfaced as a typed error the caller
    // can render an error state for (CLAUDE.md §9).
    throw new ApiError(
      0,
      "Network request failed. Is the backend reachable?",
      "NETWORK_ERROR",
      cause,
    );
  }

  const body: unknown = await response.json().catch(() => undefined);

  if (!response.ok) {
    if (response.status === 401 && "Authorization" in auth) {
      // The token we sent was rejected by the backend even though our
      // local SDK still considered it valid (revoked/rotated server-side,
      // not just expired) — hand off to the auth layer rather than
      // leaving the app silently stuck making requests that will never
      // succeed.
      notifyUnauthorized();
    }
    if (isErrorEnvelope(body)) {
      throw new ApiError(response.status, body.error.message, body.error.code, body.error.details);
    }
    throw new ApiError(response.status, `Request failed with status ${response.status}`);
  }

  return body as T;
}

export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>("GET", path, { signal });
}

export function apiPost<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>("POST", path, { body: body ?? {}, signal });
}

export function apiPatch<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  return request<T>("PATCH", path, { body: body ?? {}, signal });
}

export async function apiDelete(path: string, signal?: AbortSignal): Promise<void> {
  await request<undefined>("DELETE", path, { signal });
}

/** multipart/form-data POST — the one request shape `request()` above
 * can't express (it always JSON-encodes `body`). Used only by F9's
 * photo upload (API_SPECIFICATION.md §8), which is genuinely a file
 * upload, not a JSON payload. */
export async function apiPostFormData<T>(path: string, formData: FormData): Promise<T> {
  const url = `${env.apiBaseUrl}${path}`;
  const auth = await authHeader();
  let response: Response;

  try {
    response = await fetch(url, {
      method: "POST",
      headers: { Accept: "application/json", ...auth },
      body: formData,
    });
  } catch (cause) {
    throw new ApiError(0, "Network request failed. Is the backend reachable?", "NETWORK_ERROR", cause);
  }

  const body: unknown = await response.json().catch(() => undefined);

  if (!response.ok) {
    if (response.status === 401 && "Authorization" in auth) {
      notifyUnauthorized();
    }
    if (isErrorEnvelope(body)) {
      throw new ApiError(response.status, body.error.message, body.error.code, body.error.details);
    }
    throw new ApiError(response.status, `Request failed with status ${response.status}`);
  }

  return body as T;
}
