import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type AtRiskFilters,
  clearAvailability,
  listAtRisk,
  listAvailability,
  listMenu,
  setAvailability,
} from "@/modules/hospitality/api";
import {
  createSection,
  deleteSection,
  listPlacements,
  listSections,
  listTags,
  setPlacement,
  updateSection,
} from "@/modules/hospitality/menuApi";
import type {
  MenuAvailabilitySet,
  MenuPlacementSet,
  MenuSectionCreate,
  MenuSectionUpdate,
} from "@/modules/hospitality/types";

/** Every sellable dish with its resolved price, one page, for item labels and price prefills.
 * The inventory `useItemOptions` shape (limit 200, 60s fresh) — but this module's own endpoint,
 * so nothing here reaches into another module's hooks for a name it can already read. */
export function useMenu() {
  return useQuery({
    queryKey: ["hospitality", "menu"],
    queryFn: () => listMenu({ limit: 200 }),
    staleTime: 60_000,
    // A server holds `ticket.*` and not `menu.read` (docs §7), and this read is a label lookup on
    // the check screen — the global throwOnError (lib/queryClient.ts) would turn that 403 into a
    // full-page error and lock the module's main persona out of every check. Degrading to raw
    // item ids is the honest failure here; #180's rule is about the record a page is FOR.
    throwOnError: false,
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

// --- Menu structure (#212, D-081) ---------------------------------------------

/** The section tree. `staleTime` is long on purpose: a menu's headings change when a manager
 * rewrites the menu, not during service — the opposite clock from the 86 board above. */
export function useMenuSections() {
  return useQuery({
    queryKey: ["hospitality", "menu-sections"],
    queryFn: listSections,
    staleTime: 5 * 60_000,
  });
}

export function useMenuPlacements() {
  return useQuery({
    queryKey: ["hospitality", "menu-placements"],
    queryFn: listPlacements,
    staleTime: 5 * 60_000,
  });
}

/** Every tag the property has actually used — the picker's options, from the labels in use rather
 * than a master table somebody has to prune (D-081). */
export function useMenuTags() {
  return useQuery({
    queryKey: ["hospitality", "menu-tags"],
    queryFn: listTags,
    staleTime: 5 * 60_000,
  });
}

function invalidateStructure(queryClient: ReturnType<typeof useQueryClient>) {
  void queryClient.invalidateQueries({ queryKey: ["hospitality", "menu-sections"] });
  void queryClient.invalidateQueries({ queryKey: ["hospitality", "menu-placements"] });
  void queryClient.invalidateQueries({ queryKey: ["hospitality", "menu-tags"] });
}

export function useCreateMenuSection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: MenuSectionCreate) => createSection(payload),
    onSuccess: () => invalidateStructure(queryClient),
  });
}

export function useUpdateMenuSection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sectionId, payload }: { sectionId: string; payload: MenuSectionUpdate }) =>
      updateSection(sectionId, payload),
    onSuccess: () => invalidateStructure(queryClient),
  });
}

export function useDeleteMenuSection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sectionId: string) => deleteSection(sectionId),
    onSuccess: () => invalidateStructure(queryClient),
  });
}

/** One mutation instance serves the whole dish table — the item id is an argument, the
 * `useMoveOpportunityStage` shape. */
export function useSetMenuPlacement() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, payload }: { itemId: string; payload: MenuPlacementSet }) =>
      setPlacement(itemId, payload),
    onSuccess: () => invalidateStructure(queryClient),
  });
}
