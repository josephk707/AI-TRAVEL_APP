/**
 * API client foundation (MOBILE_ARCHITECTURE.md §9).
 *
 * Phase 1: a thin, typed fetch wrapper only. No auth token injection yet
 * (there is no auth — Phase 3) and no generated OpenAPI client yet (there
 * is no versioned product API surface to generate from — Phase 4+). This
 * establishes the single call path every later API call goes through, so
 * auth-header injection and retry logic have one place to be added later
 * instead of being bolted onto scattered fetch() calls.
 */

import { env } from "../config/env";

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

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const url = `${env.apiBaseUrl}${path}`;
  let response: Response;

  try {
    response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal,
    });
  } catch (cause) {
    // Network-level failure (no connectivity, DNS, backend down) —
    // never swallowed, always surfaced as a typed error the caller
    // can render an error state for (CLAUDE.md §9).
    throw new ApiError(0, "Network request failed. Is the backend reachable?", "NETWORK_ERROR", cause);
  }

  const body: unknown = await response.json().catch(() => undefined);

  if (!response.ok) {
    if (isErrorEnvelope(body)) {
      throw new ApiError(response.status, body.error.message, body.error.code, body.error.details);
    }
    throw new ApiError(response.status, `Request failed with status ${response.status}`);
  }

  return body as T;
}
