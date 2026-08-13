/**
 * MRP hooks (STRUCTURE §4). The run submit returns 202 JobSubmitted — the form polls the job
 * via lib/jobs and navigates to the finished run, so the mutation here just submits.
 * Planned-order actions invalidate the run detail too (firm/convert/cancel change the counts
 * a re-run would net).
 */

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelPlannedOrder,
  convertPlannedOrder,
  firmPlannedOrder,
  getMrpRun,
  listMrpRuns,
  listPlannedOrders,
  runMrp,
  type MrpRunFilters,
  type PlannedOrderFilters,
} from "@/modules/manufacturing/api";
import type { MrpRunRequest, PlannedOrderConvertRequest } from "@/modules/manufacturing/types";

export function useMrpRuns(filters: Omit<MrpRunFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["manufacturing", "mrp-runs", filters],
    queryFn: ({ pageParam }) => listMrpRuns({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useMrpRun(runId: string | undefined) {
  return useQuery({
    queryKey: ["manufacturing", "mrp-run", runId],
    queryFn: () => getMrpRun(runId as string),
    enabled: runId !== undefined,
  });
}

export function usePlannedOrders(
  runId: string | undefined,
  filters: Omit<PlannedOrderFilters, "cursor"> = {},
) {
  return useInfiniteQuery({
    queryKey: ["manufacturing", "planned-orders", runId, filters],
    queryFn: ({ pageParam }) =>
      listPlannedOrders(runId as string, { ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: runId !== undefined,
  });
}

export function useRunMrp() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: MrpRunRequest) => runMrp(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["manufacturing", "mrp-runs"] }),
  });
}

function invalidatePlanned(queryClient: ReturnType<typeof useQueryClient>, runId: string) {
  void queryClient.invalidateQueries({ queryKey: ["manufacturing", "planned-orders", runId] });
  void queryClient.invalidateQueries({ queryKey: ["manufacturing", "mrp-run", runId] });
  // A MAKE conversion creates a real production order — keep that list fresh too.
  void queryClient.invalidateQueries({ queryKey: ["manufacturing", "production-orders"] });
}

export function useFirmPlannedOrder(runId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (plannedOrderId: string) => firmPlannedOrder(plannedOrderId),
    onSuccess: () => invalidatePlanned(queryClient, runId),
  });
}

export function useConvertPlannedOrder(runId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      plannedOrderId,
      payload,
    }: {
      plannedOrderId: string;
      payload: PlannedOrderConvertRequest;
    }) => convertPlannedOrder(plannedOrderId, payload),
    onSuccess: () => invalidatePlanned(queryClient, runId),
  });
}

export function useCancelPlannedOrder(runId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (plannedOrderId: string) => cancelPlannedOrder(plannedOrderId),
    onSuccess: () => invalidatePlanned(queryClient, runId),
  });
}
