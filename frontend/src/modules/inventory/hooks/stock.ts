import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createStockMove,
  getStockMove,
  listCostLayers,
  listStockMoves,
  listStockOnHand,
  listStockValuations,
  reverseStockMove,
  type StockMoveFilters,
  type StockOnHandFilters,
  type StockValuationFilters,
} from "@/modules/inventory/api";
import type { StockMoveCreate } from "@/modules/inventory/types";

export function useStockMoves(filters: Omit<StockMoveFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["inventory", "stock-moves", filters],
    queryFn: ({ pageParam }) =>
      listStockMoves({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useStockMove(moveId: string | undefined) {
  return useQuery({
    queryKey: ["inventory", "stock-move", moveId],
    queryFn: () => getStockMove(moveId as string),
    enabled: moveId !== undefined,
  });
}

export function useCreateStockMove() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: StockMoveCreate) => createStockMove(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "stock-moves"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory", "stock-on-hand"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory", "stock-valuations"] });
    },
  });
}

export function useReverseStockMove() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (moveId: string) => reverseStockMove(moveId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "stock-moves"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory", "stock-on-hand"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory", "stock-valuations"] });
    },
  });
}

export function useStockOnHand(filters: Omit<StockOnHandFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["inventory", "stock-on-hand", filters],
    queryFn: ({ pageParam }) =>
      listStockOnHand({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useStockValuations(filters: Omit<StockValuationFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["inventory", "stock-valuations", filters],
    queryFn: ({ pageParam }) =>
      listStockValuations({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useCostLayers(itemId: string | undefined, warehouseId: string | undefined) {
  return useQuery({
    queryKey: ["inventory", "cost-layers", itemId, warehouseId],
    queryFn: () =>
      listCostLayers(itemId as string, { ...(warehouseId ? { warehouse_id: warehouseId } : {}), limit: 200 }),
    enabled: itemId !== undefined && warehouseId !== undefined,
  });
}
