import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type BinFilters,
  createBin,
  createWarehouse,
  getBin,
  getWarehouse,
  listBins,
  listWarehouses,
  updateBin,
  updateWarehouse,
  type WarehouseFilters,
} from "@/modules/inventory/api";
import type { BinCreate, BinUpdate, WarehouseCreate, WarehouseUpdate } from "@/modules/inventory/types";

export function useWarehouses(filters: Omit<WarehouseFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["inventory", "warehouses", filters],
    queryFn: ({ pageParam }) =>
      listWarehouses({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useWarehouse(warehouseId: string | undefined) {
  return useQuery({
    queryKey: ["inventory", "warehouse", warehouseId],
    queryFn: () => getWarehouse(warehouseId as string),
    enabled: warehouseId !== undefined,
  });
}

export function useWarehouseOptions() {
  return useQuery({
    queryKey: ["inventory", "warehouses", "options"],
    queryFn: () => listWarehouses({ limit: 200 }),
    staleTime: 60_000,
  });
}

/** Every warehouse for resolving warehouse_id -> code/name on read-only views (valuation).
 * Same query as useWarehouseOptions — shares the cache, just a differently-named consumer. */
export function useWarehouseLookup() {
  return useQuery({
    queryKey: ["inventory", "warehouses", "options"],
    queryFn: () => listWarehouses({ limit: 200 }),
    staleTime: 60_000,
  });
}

export function useCreateWarehouse() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: WarehouseCreate) => createWarehouse(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "warehouses"] });
    },
  });
}

export function useUpdateWarehouse(warehouseId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: WarehouseUpdate) => updateWarehouse(warehouseId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "warehouses"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory", "warehouse", warehouseId] });
    },
  });
}

export function useBins(filters: Omit<BinFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["inventory", "bins", filters],
    queryFn: ({ pageParam }) =>
      listBins({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useBin(binId: string | undefined) {
  return useQuery({
    queryKey: ["inventory", "bin", binId],
    queryFn: () => getBin(binId as string),
    enabled: binId !== undefined,
  });
}

/** All bins for a warehouse, unpaginated — the bin picker on the move form. */
export function useBinOptions(warehouseId: string | undefined) {
  return useQuery({
    queryKey: ["inventory", "bins", "options", warehouseId],
    queryFn: () => listBins({ warehouse_id: warehouseId as string, limit: 200 }),
    enabled: warehouseId !== undefined,
    staleTime: 60_000,
  });
}

/** Every bin across every warehouse for resolving bin_id -> code/name on read-only views
 * (on-hand, move detail) — mirrors useItemLookup. */
export function useBinLookup() {
  return useQuery({
    queryKey: ["inventory", "bins", "lookup"],
    queryFn: () => listBins({ limit: 200 }),
    staleTime: 60_000,
  });
}

export function useCreateBin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BinCreate) => createBin(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "bins"] });
    },
  });
}

export function useUpdateBin(binId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BinUpdate) => updateBin(binId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["inventory", "bins"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory", "bin", binId] });
    },
  });
}
