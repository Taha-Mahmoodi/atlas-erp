/**
 * Session state for the D-008 auth flow: the access token lives in MEMORY only (never
 * localStorage — XSS cannot exfiltrate what isn't stored), the refresh token lives in the
 * HttpOnly cookie the backend scopes to /api/v1/auth. `login`/`refreshAccessToken`/`logout`
 * are the only session mutations; subscribers (the router guard, the app shell) are
 * notified on every change.
 */

const BASE_URL = "/api/v1/auth";

interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface LoginRequest {
  tenant_slug: string;
  email: string;
  password: string;
}

let accessToken: string | null = null;
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of listeners) listener();
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function isAuthenticated(): boolean {
  return accessToken !== null;
}

/** Subscribe to session changes (login/refresh/logout). Returns the unsubscribe. */
export function onSessionChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function clearSession(): void {
  if (accessToken === null) return;
  accessToken = null;
  notify();
}

export async function login(payload: LoginRequest): Promise<void> {
  const response = await fetch(`${BASE_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
    credentials: "same-origin",
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? "Login failed");
  }
  const tokens = (await response.json()) as TokenResponse;
  accessToken = tokens.access_token;
  notify();
}

/**
 * Rotate the refresh cookie into a fresh access token. Returns false when the session is
 * gone (expired/revoked refresh) — callers then route to login. Used by the api client's
 * one-shot 401 retry and by app boot to resume a session without re-entering credentials.
 *
 * Single-flight (#158): D-008 rotates the refresh token on every use, so two concurrent
 * POSTs (AuthGate's boot refresh double-fired under StrictMode, plus the api client's 401
 * retry) race and the loser 401s in the console. All concurrent callers share one request.
 */
let refreshInFlight: Promise<boolean> | null = null;

export function refreshAccessToken(): Promise<boolean> {
  refreshInFlight ??= doRefreshAccessToken().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

async function doRefreshAccessToken(): Promise<boolean> {
  const response = await fetch(`${BASE_URL}/refresh`, {
    method: "POST",
    headers: { Accept: "application/json" },
    credentials: "same-origin",
  });
  if (!response.ok) return false;
  const tokens = (await response.json()) as TokenResponse;
  accessToken = tokens.access_token;
  notify();
  return true;
}

export async function logout(): Promise<void> {
  await fetch(`${BASE_URL}/logout`, {
    method: "POST",
    headers: { Accept: "application/json" },
    credentials: "same-origin",
  }).catch(() => undefined); // best effort — the local session clears regardless
  clearSession();
}
