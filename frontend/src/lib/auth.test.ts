import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearSession, getAccessToken, login, logout, refreshAccessToken } from "@/lib/auth";
import { queryClient } from "@/lib/queryClient";

function tokenResponse(token: string): Response {
  return new Response(JSON.stringify({ access_token: token, token_type: "bearer" }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

const CREDENTIALS = { tenant_slug: "acme", email: "owner@acme.test", password: "pw" };

beforeEach(() => {
  // Normalize to a signed-out session and an empty cache; module state persists per file.
  vi.stubGlobal("fetch", vi.fn(async () => tokenResponse("setup")));
  clearSession();
  queryClient.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("refreshAccessToken single-flight (#158)", () => {
  it("coalesces concurrent calls into a single POST /auth/refresh", async () => {
    let resolveFetch!: (response: Response) => void;
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => (resolveFetch = resolve)));
    vi.stubGlobal("fetch", fetchMock);

    // AuthGate's StrictMode double-mount + the api client's 401 retry overlap in practice.
    const first = refreshAccessToken();
    const second = refreshAccessToken();
    resolveFetch(tokenResponse("t1"));

    await expect(first).resolves.toBe(true);
    await expect(second).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(getAccessToken()).toBe("t1");
  });

  it("issues a fresh request once the previous refresh has settled", async () => {
    const fetchMock = vi.fn(async () => tokenResponse("t2"));
    vi.stubGlobal("fetch", fetchMock);

    await refreshAccessToken();
    await refreshAccessToken();

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("shares the failure too — both concurrent callers see false", async () => {
    let resolveFetch!: (response: Response) => void;
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => (resolveFetch = resolve)));
    vi.stubGlobal("fetch", fetchMock);

    const first = refreshAccessToken();
    const second = refreshAccessToken();
    resolveFetch(new Response(null, { status: 401 }));

    await expect(first).resolves.toBe(false);
    await expect(second).resolves.toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("query cache clearing on session transitions (#157)", () => {
  it("clears the cache on a successful login", async () => {
    queryClient.setQueryData(["tenant-a", "items"], ["tenant A secret"]);

    await login(CREDENTIALS);

    expect(getAccessToken()).toBe("setup");
    expect(queryClient.getQueryData(["tenant-a", "items"])).toBeUndefined();
  });

  it("clears the cache on sign-out", async () => {
    await login(CREDENTIALS);
    queryClient.setQueryData(["tenant-a", "items"], ["tenant A secret"]);

    await logout();

    expect(getAccessToken()).toBeNull();
    expect(queryClient.getQueryData(["tenant-a", "items"])).toBeUndefined();
  });

  it("does NOT clear the cache on a mid-session token refresh", async () => {
    await login(CREDENTIALS);
    queryClient.setQueryData(["reports", "list"], ["still valid"]);

    await refreshAccessToken();

    expect(queryClient.getQueryData(["reports", "list"])).toEqual(["still valid"]);
  });
});
