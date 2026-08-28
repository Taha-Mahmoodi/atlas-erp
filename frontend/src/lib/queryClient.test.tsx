/**
 * Regression test for issue #227: the docflow edges the "Document flow" section exists to show
 * are written at POST time, and nothing invalidated `["documents", <id>, "chain"]`. With
 * `staleTime: 30_000` the operator clicked Post and kept reading the pre-post chain — a lone
 * node saying, in writing, that the document produced nothing.
 *
 * The mutation here carries its OWN `onSuccess`, exactly as every post hook does: that is the
 * reason the invalidation lives on the `mutationCache` rather than in
 * `defaultOptions.mutations`, where a per-mutation callback would replace it.
 */

import { QueryClientProvider, useMutation, useQuery } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { queryClient } from "@/lib/queryClient";

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("queryClient", () => {
  it("refetches a mounted document chain after any successful mutation (issue #227)", async () => {
    const fetchChain = vi.fn().mockResolvedValue({ nodes: [], edges: [] });
    const ownOnSuccess = vi.fn();

    const { result } = renderHook(
      () => ({
        chain: useQuery({ queryKey: ["documents", "doc-delivery", "chain"], queryFn: fetchChain }),
        post: useMutation({ mutationFn: () => Promise.resolve("POSTED"), onSuccess: ownOnSuccess }),
      }),
      { wrapper },
    );

    await waitFor(() => expect(fetchChain).toHaveBeenCalledTimes(1));

    await result.current.post.mutateAsync(undefined);

    await waitFor(() => expect(fetchChain).toHaveBeenCalledTimes(2));
    expect(ownOnSuccess).toHaveBeenCalledTimes(1);

    queryClient.clear();
  });
});
