/**
 * TanStack Query hooks for the quality module (STRUCTURE §4). Flat file — well under the
 * ~400-line split threshold the bigger modules crossed.
 */

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelInspectionLot,
  decideInspectionLot,
  getInspectionLot,
  type InspectionLotFilters,
  listInspectionLots,
} from "@/modules/quality/api";
import type { InspectionDecidePayload } from "@/modules/quality/types";

export function useInspectionLots(filters: Omit<InspectionLotFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["quality", "inspection-lots", filters],
    queryFn: ({ pageParam }) =>
      listInspectionLots({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useInspectionLot(lotId: string | undefined) {
  return useQuery({
    queryKey: ["quality", "inspection-lot", lotId],
    queryFn: () => getInspectionLot(lotId as string),
    enabled: lotId !== undefined,
  });
}

function invalidateLot(queryClient: ReturnType<typeof useQueryClient>, lotId: string) {
  void queryClient.invalidateQueries({ queryKey: ["quality", "inspection-lots"] });
  void queryClient.invalidateQueries({ queryKey: ["quality", "inspection-lot", lotId] });
}

export function useDecideInspectionLot(lotId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: InspectionDecidePayload) => decideInspectionLot(lotId, payload),
    onSuccess: () => invalidateLot(queryClient, lotId),
  });
}

export function useCancelInspectionLot(lotId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelInspectionLot(lotId),
    onSuccess: () => invalidateLot(queryClient, lotId),
  });
}
