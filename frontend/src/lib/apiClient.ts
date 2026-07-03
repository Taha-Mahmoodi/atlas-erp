/**
 * The ONLY place `fetch` appears (STRUCTURE §4). Every request goes through `api`:
 * JSON in/out, the backend's consistent error envelope decoded into `ApiError`, the
 * bearer token attached from `auth`, and a one-shot refresh-and-retry on 401 (the
 * D-008 rotating-refresh flow). Module `api.ts` files build on these helpers only.
 */

import { clearSession, getAccessToken, refreshAccessToken } from "@/lib/auth";

const BASE_URL = "/api/v1";

/** The backend's error envelope: { error: { code, message, details } }. */
export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown> | undefined;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }
}

/** For a Pydantic validation error (`common.validation_error`), `details` is an array of
 * `{field, message, type}` — every OTHER error code's `details` is a plain object (or
 * absent). `ApiError.message` alone is just the generic "Request validation failed" for the
 * array case, which tells the user nothing about which field was wrong — this pulls the
 * specific per-field messages out when they're present. */
export function getErrorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  if (Array.isArray(error.details)) {
    const fieldMessages = error.details
      .filter((entry): entry is Record<string, unknown> => typeof entry === "object" && entry !== null)
      .map((entry) => (typeof entry.message === "string" ? entry.message : null))
      .filter((message): message is string => message !== null);
    if (fieldMessages.length > 0) return fieldMessages.join("; ");
  }
  return error.message || fallback;
}

/** Keyset page envelope (D-014) — mirrors backend `Page[T]`, snake_case untranslated. */
export interface Page<T> {
  items: T[];
  next_cursor: string | null;
  limit: number;
}

export interface RequestOptions {
  /** Query parameters; null/undefined entries are dropped. */
  params?: Record<string, string | number | boolean | null | undefined>;
  /** D-013 idempotency key for document-creating POSTs. */
  idempotencyKey?: string;
  signal?: AbortSignal;
}

function buildUrl(path: string, params?: RequestOptions["params"]): string {
  const url = BASE_URL + path;
  if (!params) return url;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined) query.set(key, String(value));
  }
  const qs = query.toString();
  return qs ? `${url}?${qs}` : url;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody = { code: "unknown", message: response.statusText };
  try {
    const json = (await response.json()) as { error?: ApiErrorBody };
    if (json.error) body = json.error;
  } catch {
    // Non-JSON error body (proxy page, empty response) — keep the status text.
  }
  return new ApiError(response.status, body);
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options: RequestOptions = {},
  retryOn401 = true,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;

  const response = await fetch(buildUrl(path, options.params), {
    method,
    headers,
    body: body === undefined ? null : JSON.stringify(body),
    credentials: "same-origin", // the refresh cookie is scoped to /api/v1/auth
    ...(options.signal ? { signal: options.signal } : {}),
  });

  if (response.status === 401 && retryOn401 && !path.startsWith("/auth/")) {
    // Access token expired mid-session: one refresh attempt, then one retry.
    const refreshed = await refreshAccessToken();
    if (refreshed) return request<T>(method, path, body, options, false);
    clearSession();
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>("GET", path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>("POST", path, body, options),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>("PUT", path, body, options),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>("PATCH", path, body, options),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>("DELETE", path, undefined, options),
};

/** A fresh D-013 idempotency key for document-creating POSTs. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
