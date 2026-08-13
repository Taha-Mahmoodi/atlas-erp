/**
 * TanStack Query hooks for payroll runs (PLAN 10.4, D-055): compute a DRAFT gross→net run,
 * post its consolidated finance journal, or cancel a draft. Posting invalidates finance's
 * journal list since the journal posts in the same transaction.
 */

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelPayrollRun,
  createPayrollRun,
  getPayrollRun,
  listPayrollRuns,
  type PayrollRunFilters,
  postPayrollRun,
} from "@/modules/hr/api";
import type { PayrollRunCreate, PayrollRunPost } from "@/modules/hr/types";

export function usePayrollRuns(filters: Omit<PayrollRunFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["hr", "payroll-runs", filters],
    queryFn: ({ pageParam }) => listPayrollRuns({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function usePayrollRun(runId: string | undefined) {
  return useQuery({
    queryKey: ["hr", "payroll-run", runId],
    queryFn: () => getPayrollRun(runId as string),
    enabled: runId !== undefined,
  });
}

function invalidatePayrollRuns(queryClient: ReturnType<typeof useQueryClient>, runId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["hr", "payroll-runs"] });
  if (runId) void queryClient.invalidateQueries({ queryKey: ["hr", "payroll-run", runId] });
}

export function useCreatePayrollRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PayrollRunCreate) => createPayrollRun(payload),
    onSuccess: () => invalidatePayrollRuns(queryClient),
  });
}

export function usePostPayrollRun(runId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PayrollRunPost) => postPayrollRun(runId, payload),
    onSuccess: () => {
      invalidatePayrollRuns(queryClient, runId);
      void queryClient.invalidateQueries({ queryKey: ["finance", "journal-entries"] });
    },
  });
}

export function useCancelPayrollRun(runId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelPayrollRun(runId),
    onSuccess: () => invalidatePayrollRuns(queryClient, runId),
  });
}
