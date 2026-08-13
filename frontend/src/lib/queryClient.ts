/**
 * The single TanStack Query client. Defaults tuned for an ERP: reference data stays fresh
 * for 30s (list pages navigate a lot; refetch-on-focus covers staleness), mutations never
 * retry automatically (a retried POST without its idempotency key could double-post — the
 * api client's D-013 keys protect creates, but retry policy belongs to each call site),
 * and 4xx responses never retry (they are deterministic).
 */

import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/apiClient";
import { isAuthenticated, onSessionChange } from "@/lib/auth";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status < 500) return false;
        return failureCount < 2;
      },
    },
    mutations: { retry: false },
  },
});

// Cross-tenant leak guard (#157): sign-out and sign-in must never serve the previous
// session's cached data (useMe is staleTime:Infinity; lists stay fresh 30s). Any
// authenticated-state TRANSITION drops the whole cache; a mid-session token refresh keeps
// the state true→true and leaves the cache alone.
let wasAuthenticated = isAuthenticated();
onSessionChange(() => {
  const authenticated = isAuthenticated();
  if (authenticated !== wasAuthenticated) queryClient.clear();
  wasAuthenticated = authenticated;
});
