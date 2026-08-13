import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createItem,
  createItemCategory,
  createUom,
  createUomConversion,
  getItem,
  getItemCategory,
  getUom,
  type ItemCategoryFilters,
  type ItemFilters,
  listItemCategories,
  listItems,
  listUomConversions,
  listUoms,
  updateItem,
  updateItemCategory,
  updateUom,
  type UomFilters,
} from "@/modules/inventory/api";
import type {
  ItemCategoryCreate,
  ItemCategoryUpdate,
  ItemCreate,
  ItemUpdate,
  UomConversionCreate,
  UomCreate,
  UomUpdate,
} from "@/modules/inventory/types";

export function useItemCategories(filters: Omit<ItemCategoryFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["inventory", "item-categories", filters],
    queryFn: ({ pageParam }) =>
      listItemCategories({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useItemCategory(categoryId: string | undefined) {
  return useQuery({
    queryKey: ["inventory", "item-category", categoryId],
    queryFn: () => getItemCategory(categoryId as string),
    enabled: categoryId !== undefined,
  });
}

/** All categories for a picker — v1 keeps this to one page, mirrors finance's
 * useAccountGroups (reference data, rarely outgrows a single page). */
export function useItemCategoryOptions() {
  return useQuery({
    queryKey: ["inventory", "item-categories", "options"],
    queryFn: () => listItemCategories({ limit: 200 }),
    staleTime: 60_000,
  });
}

export function useCreateItemCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ItemCategoryCreate) => createItemCategory(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "item-categories"] });
    },
  });
}

export function useUpdateItemCategory(categoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ItemCategoryUpdate) => updateItemCategory(categoryId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "item-categories"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory", "item-category", categoryId] });
    },
  });
}

export function useUoms(filters: Omit<UomFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["inventory", "uoms", filters],
    queryFn: ({ pageParam }) =>
      listUoms({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useUom(uomId: string | undefined) {
  return useQuery({
    queryKey: ["inventory", "uom", uomId],
    queryFn: () => getUom(uomId as string),
    enabled: uomId !== undefined,
  });
}

export function useUomOptions() {
  return useQuery({
    queryKey: ["inventory", "uoms", "options"],
    queryFn: () => listUoms({ limit: 200 }),
    staleTime: 60_000,
  });
}

export function useCreateUom() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UomCreate) => createUom(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "uoms"] });
    },
  });
}

export function useUpdateUom(uomId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UomUpdate) => updateUom(uomId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "uoms"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory", "uom", uomId] });
    },
  });
}

export function useItems(filters: Omit<ItemFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["inventory", "items", filters],
    queryFn: ({ pageParam }) =>
      listItems({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useItem(itemId: string | undefined) {
  return useQuery({
    queryKey: ["inventory", "item", itemId],
    queryFn: () => getItem(itemId as string),
    enabled: itemId !== undefined,
  });
}

/** All active items for a picker (a plain select, not paginated — mirrors finance's
 * useAccountOptions; a searchable combobox is worth adding once a catalog outgrows one page). */
export function useItemOptions() {
  return useQuery({
    queryKey: ["inventory", "items", "options"],
    queryFn: () => listItems({ is_active: true, limit: 200 }),
    staleTime: 60_000,
  });
}

/** Every item (no filters) for resolving item_id -> code/name on read-only views — a posted
 * move may reference a since-deactivated item. Mirrors finance's useAccountLookup. */
export function useItemLookup() {
  return useQuery({
    queryKey: ["inventory", "items", "lookup"],
    queryFn: () => listItems({ limit: 200 }),
    staleTime: 60_000,
  });
}

export function useCreateItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ItemCreate) => createItem(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "items"] });
    },
  });
}

export function useUpdateItem(itemId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ItemUpdate) => updateItem(itemId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "items"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory", "item", itemId] });
    },
  });
}

export function useUomConversions(itemId: string | undefined) {
  return useQuery({
    queryKey: ["inventory", "uom-conversions", itemId],
    queryFn: () => listUomConversions(itemId as string),
    enabled: itemId !== undefined,
  });
}

export function useCreateUomConversion(itemId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UomConversionCreate) => createUomConversion(itemId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "uom-conversions", itemId] });
    },
  });
}
