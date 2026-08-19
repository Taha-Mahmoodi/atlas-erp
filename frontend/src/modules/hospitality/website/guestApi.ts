/**
 * The guest site's HTTP layer — the SECOND and last place `fetch` appears in this repo, and the
 * exception STRUCTURE §4 now names.
 *
 * `lib/apiClient` cannot serve this surface: it attaches the staff access token and runs the
 * D-008 refresh-and-retry on 401. A guest has no session and never will. The credential here is
 * the property's machine API key (D-069), and it is attached by **nginx**, not by this file —
 * `/guest-api/*` is an allowlist of the five endpoints docs/api.md's website contract names, and
 * the key never reaches the browser. That is the whole reason the guest site is its own origin.
 *
 * Errors surface as `GuestApiError` carrying the backend's error envelope, because two of this
 * site's refusals are ordinary answers a guest must read rather than crashes: an 86'd dish
 * (`hospitality.item_unavailable`) and a full slot (`hospitality.slot_full`, whose `details`
 * carry the nearest bookable alternatives).
 */

const BASE = "/guest-api";

export interface GuestApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export class GuestApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown> | undefined;

  constructor(status: number, body: GuestApiErrorBody) {
    super(body.message);
    this.name = "GuestApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(BASE + path, init);
  if (!response.ok) {
    let body: GuestApiErrorBody = { code: "unknown", message: response.statusText };
    try {
      const json = (await response.json()) as { error?: GuestApiErrorBody };
      if (json.error) body = json.error;
    } catch {
      /* a proxy error page is not JSON — the status line is all there is */
    }
    throw new GuestApiError(response.status, body);
  }
  return (await response.json()) as T;
}

export function guestGet<T>(path: string, params?: Record<string, string>): Promise<T> {
  const query = params ? `?${new URLSearchParams(params).toString()}` : "";
  return request<T>(path + query);
}

/**
 * Every write here creates a document, so every write carries a FRESH idempotency key (D-013,
 * rule 4 of the website contract): a key is scoped to its endpoint and its request target, so
 * reusing one across two orders is a 422, never a silent replay.
 *
 * A retry of the SAME submit must reuse its key — which is why the caller passes it in rather
 * than having it minted here, where a re-render would mint a second one and duplicate the order.
 */
export function guestPost<T>(path: string, body: unknown, idempotencyKey: string): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(body),
  });
}

/** One key per submit attempt, minted when the guest presses the button and held across retries. */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}
