/**
 * The single TanStack Query client. Defaults tuned for an ERP: reference data stays fresh
 * for 30s (list pages navigate a lot; refetch-on-focus covers staleness), mutations never
 * retry automatically (a retried POST without its idempotency key could double-post — the
 * api client's D-013 keys protect creates, but retry policy belongs to each call site),
 * and 4xx responses never retry (they are deterministic).
 */

import { MutationCache, QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/apiClient";
import { isAuthenticated, onSessionChange } from "@/lib/auth";

export const queryClient = new QueryClient({
  // #227: a document's flow chain (`["documents", <id>, "chain"]`, lib/docflow.ts) is written
  // by `core/docflow.py` from inside EVERY module's service and event handlers — posting one
  // delivery sets the registry status, links order→delivery, and lets inventory add the move
  // edges and finance the COGS journal. There is therefore no enumerable set of mutations that
  // change a chain, and a post hook that forgot to invalidate would leave the audit trail
  // asserting "this document produced nothing". The registry is cross-cutting, so its
  // invalidation lives here with the other cross-cutting cache policies rather than being
  // re-remembered in every module's hooks. `mutationCache` (not `defaultOptions.mutations`)
  // because a per-mutation `onSuccess` REPLACES the default one — these fire in addition to it.
  // The key matches only `useDocumentFlow`, so at most one small query refetches, and only
  // while a document-flow section is actually on screen.
  mutationCache: new MutationCache({
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["documents"] }),
  }),
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status < 500) return false;
        return failureCount < 2;
      },
      // #180: a 4xx on a read means "this record can't be shown" — not found, not readable,
      // or an unreadable id. Throwing it to RouteErrorBoundary is the single-point fix for
      // pages that used to render a blank editable form or spin forever instead. 401 is
      // excluded: apiClient owns the refresh-and-retry flow and AuthGate owns the fallout.
      // 5xx and network errors stay inline and retryable rather than replacing the page.
      throwOnError: (error) =>
        error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 401,
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
