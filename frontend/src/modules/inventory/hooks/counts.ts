import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelStockCount,
  createStockCount,
  getStockCount,
  getStockCountVariancePreview,
  listStockCountLines,
  listStockCounts,
  postStockCount,
  recordCountedQuantity,
  type StockCountFilters,
} from "@/modules/inventory/api";
import type { StockCountCreate, StockCountLineCountUpdate } from "@/modules/inventory/types";

export function useStockCounts(filters: Omit<StockCountFilters, "cursor"> = {}) {
  return useQuery({
    queryKey: ["inventory", "stock-counts", filters],
    queryFn: () => listStockCounts({ ...filters, limit: 200 }),
  });
}

export function useStockCount(countId: string | undefined) {
  return useQuery({
    queryKey: ["inventory", "stock-count", countId],
    queryFn: () => getStockCount(countId as string),
    enabled: countId !== undefined,
  });
}

export function useStockCountLines(countId: string | undefined) {
  return useQuery({
    queryKey: ["inventory", "stock-count-lines", countId],
    queryFn: () => listStockCountLines(countId as string, { limit: 500 }),
    enabled: countId !== undefined,
  });
}

/** Not fetched eagerly — a physical count can have thousands of lines (#78), so the preview
 * loads only when the operator explicitly asks to see it, one page at a time. */
export function useStockCountVariancePreview(countId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["inventory", "stock-count-variance-preview", countId],
    queryFn: () => getStockCountVariancePreview(countId, { limit: 200 }),
    enabled,
  });
}

export function useCreateStockCount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: StockCountCreate) => createStockCount(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "stock-counts"] });
    },
  });
}

export function useRecordCountedQuantity(countId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ lineId, payload }: { lineId: string; payload: StockCountLineCountUpdate }) =>
      recordCountedQuantity(countId, lineId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "stock-count", countId] });
      void queryClient.invalidateQueries({ queryKey: ["inventory", "stock-count-lines", countId] });
    },
  });
}

export function usePostStockCount() {
  return useMutation({
    mutationFn: (countId: string) => postStockCount(countId),
  });
}

export function useCancelStockCount(countId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelStockCount(countId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "stock-counts"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory", "stock-count", countId] });
    },
  });
}
