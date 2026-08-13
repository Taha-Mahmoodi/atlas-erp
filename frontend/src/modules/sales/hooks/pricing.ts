import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createPriceList,
  createPriceListItem,
  deletePriceListItem,
  getPriceList,
  getPriceQuote,
  listPriceListItems,
  listPriceLists,
  type PriceListFilters,
  type PriceQuoteParams,
  updatePriceList,
} from "@/modules/sales/api";
import type { PriceListCreate, PriceListItemCreate, PriceListUpdate } from "@/modules/sales/types";

export function usePriceLists(filters: Omit<PriceListFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["sales", "price-lists", filters],
    queryFn: ({ pageParam }) => listPriceLists({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function usePriceList(priceListId: string | undefined) {
  return useQuery({
    queryKey: ["sales", "price-list", priceListId],
    queryFn: () => getPriceList(priceListId as string),
    enabled: priceListId !== undefined,
  });
}

function invalidatePriceLists(queryClient: ReturnType<typeof useQueryClient>, priceListId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["sales", "price-lists"] });
  if (priceListId) void queryClient.invalidateQueries({ queryKey: ["sales", "price-list", priceListId] });
}

export function useCreatePriceList() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PriceListCreate) => createPriceList(payload),
    onSuccess: () => invalidatePriceLists(queryClient),
  });
}

export function useUpdatePriceList(priceListId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PriceListUpdate) => updatePriceList(priceListId, payload),
    onSuccess: () => invalidatePriceLists(queryClient, priceListId),
  });
}

export function usePriceListItems(priceListId: string) {
  return useQuery({
    queryKey: ["sales", "price-list-items", priceListId],
    queryFn: () => listPriceListItems(priceListId),
  });
}

export function useCreatePriceListItem(priceListId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PriceListItemCreate) => createPriceListItem(priceListId, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["sales", "price-list-items", priceListId] }),
  });
}

export function useDeletePriceListItem(priceListId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => deletePriceListItem(priceListId, itemId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["sales", "price-list-items", priceListId] }),
  });
}

// --- Price quote (read-only simulation, no persisted document) --------------------

export function usePriceQuote(params: PriceQuoteParams | undefined) {
  return useQuery({
    queryKey: ["sales", "price-quote", params],
    queryFn: () => getPriceQuote(params as PriceQuoteParams),
    enabled: params !== undefined,
  });
}
