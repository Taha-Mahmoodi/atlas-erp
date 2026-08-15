import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type AtRiskFilters,
  clearAvailability,
  listAtRisk,
  listAvailability,
  listMenu,
  setAvailability,
} from "@/modules/hospitality/api";
import type { MenuAvailabilitySet } from "@/modules/hospitality/types";

/** Every sellable dish with its resolved price, one page, for item labels and price prefills.
 * The inventory `useItemOptions` shape (limit 200, 60s fresh) — but this module's own endpoint,
 * so nothing here reaches into another module's hooks for a name it can already read. */
export function useMenu() {
  return useQuery({
    queryKey: ["hospitality", "menu"],
    queryFn: () => listMenu({ limit: 200 }),
    staleTime: 60_000,
  });
}

/** The 86 board. Infinite rather than a single query only because the endpoint's own contract
 * says a property past MAX_LIMIT overrides gets a non-null cursor a client MUST follow —
 * ignoring it would read a truncated board as "everything else is available". */
export function useAvailabilityBoard() {
  return useInfiniteQuery({
    queryKey: ["hospitality", "availability"],
    queryFn: ({ pageParam }) => listAvailability(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useAtRisk(filters: AtRiskFilters = {}) {
  return useQuery({
    queryKey: ["hospitality", "at-risk", filters],
    queryFn: () => listAtRisk(filters),
  });
}

function invalidateAvailability(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["hospitality", "availability"] });
  // 86ing a dish changes what the at-risk scan is still warning about.
  void queryClient.invalidateQueries({ queryKey: ["hospitality", "at-risk"] });
}

/** The item id is a mutation argument, so ONE hook instance serves a whole board of rows. */
export function useSetAvailability() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: MenuAvailabilitySet }) =>
      setAvailability(itemId, payload),
    onSuccess: () => invalidateAvailability(queryClient),
  });
}

export function useClearAvailability() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => clearAvailability(itemId),
    onSuccess: () => invalidateAvailability(queryClient),
  });
}
