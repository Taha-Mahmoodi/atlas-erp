import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  activateAsset,
  type AssetFilters,
  createAsset,
  type DepreciationRunFilters,
  getAsset,
  getAssetRegister,
  getDepreciationRun,
  listAssets,
  listDepreciationEntries,
  listDepreciationRuns,
  listFiscalPeriods,
  runDepreciation,
  updateAsset,
} from "@/modules/finance/api";
import type {
  AssetActivateRequest,
  AssetCreate,
  AssetUpdate,
  DepreciationRunRequest,
} from "@/modules/finance/types";

export function useAssets(filters: Omit<AssetFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["finance", "assets", filters],
    queryFn: ({ pageParam }) =>
      listAssets({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useAsset(assetId: string | undefined) {
  return useQuery({
    queryKey: ["finance", "asset", assetId],
    queryFn: () => getAsset(assetId as string),
    enabled: assetId !== undefined,
  });
}

export function useCreateAsset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AssetCreate) => createAsset(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "assets"] });
    },
  });
}

export function useUpdateAsset(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AssetUpdate) => updateAsset(assetId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "assets"] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "asset", assetId] });
    },
  });
}

export function useActivateAsset(assetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AssetActivateRequest) => activateAsset(assetId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "assets"] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "asset", assetId] });
    },
  });
}

export function useRunDepreciation() {
  return useMutation({
    mutationFn: (payload: DepreciationRunRequest) => runDepreciation(payload),
  });
}

export function useDepreciationRuns(filters: Omit<DepreciationRunFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["finance", "depreciation-runs", filters],
    queryFn: ({ pageParam }) =>
      listDepreciationRuns({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useDepreciationRun(runId: string | undefined) {
  return useQuery({
    queryKey: ["finance", "depreciation-run", runId],
    queryFn: () => getDepreciationRun(runId as string),
    enabled: runId !== undefined,
  });
}

export function useDepreciationEntries(runId: string | undefined) {
  return useQuery({
    queryKey: ["finance", "depreciation-entries", runId],
    queryFn: () => listDepreciationEntries(runId as string, { limit: 200 }),
    enabled: runId !== undefined,
  });
}

export function useAssetRegister(asOf: string) {
  return useQuery({
    queryKey: ["finance", "asset-register", asOf],
    queryFn: () => getAssetRegister(asOf),
  });
}

export function useFiscalPeriods() {
  return useQuery({
    queryKey: ["finance", "fiscal-periods"],
    queryFn: () => listFiscalPeriods({ limit: 200 }),
    staleTime: 5 * 60_000,
  });
}
