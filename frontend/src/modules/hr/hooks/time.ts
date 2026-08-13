/**
 * TanStack Query hooks for time tracking (PLAN 10.3): timesheets, their nested time entries
 * (add/remove on a DRAFT), the submit/approve/reject/reopen flow, and the cost-centre / project
 * allocation report over APPROVED time.
 */

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addTimeEntry,
  approveTimesheet,
  cancelTimesheet,
  createTimesheet,
  getTimeAllocation,
  getTimesheet,
  listTimeEntries,
  listTimesheets,
  rejectTimesheet,
  removeTimeEntry,
  submitTimesheet,
  type TimesheetFilters,
} from "@/modules/hr/api";
import type {
  AllocationDimension,
  TimeEntryCreate,
  TimesheetCreate,
  TimesheetDecision,
} from "@/modules/hr/types";

// --- Timesheets ----------------------------------------------------------------

export function useTimesheets(filters: Omit<TimesheetFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["hr", "timesheets", filters],
    queryFn: ({ pageParam }) => listTimesheets({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useTimesheet(timesheetId: string | undefined) {
  return useQuery({
    queryKey: ["hr", "timesheet", timesheetId],
    queryFn: () => getTimesheet(timesheetId as string),
    enabled: timesheetId !== undefined,
  });
}

function invalidateTimesheets(queryClient: ReturnType<typeof useQueryClient>, timesheetId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["hr", "timesheets"] });
  if (timesheetId) {
    void queryClient.invalidateQueries({ queryKey: ["hr", "timesheet", timesheetId] });
    void queryClient.invalidateQueries({ queryKey: ["hr", "time-entries", timesheetId] });
  }
}

export function useCreateTimesheet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: TimesheetCreate) => createTimesheet(payload),
    onSuccess: () => invalidateTimesheets(queryClient),
  });
}

export function useSubmitTimesheet(timesheetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => submitTimesheet(timesheetId),
    onSuccess: () => invalidateTimesheets(queryClient, timesheetId),
  });
}

export function useApproveTimesheet(timesheetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: TimesheetDecision) => approveTimesheet(timesheetId, payload),
    onSuccess: () => {
      invalidateTimesheets(queryClient, timesheetId);
      // Approved entries become eligible for the allocation report.
      void queryClient.invalidateQueries({ queryKey: ["hr", "time-allocation"] });
    },
  });
}

export function useRejectTimesheet(timesheetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: TimesheetDecision) => rejectTimesheet(timesheetId, payload),
    onSuccess: () => invalidateTimesheets(queryClient, timesheetId),
  });
}

/** The backend's "cancel" verb: reopen a SUBMITTED timesheet to DRAFT for edit + resubmit. */
export function useReopenTimesheet(timesheetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelTimesheet(timesheetId),
    onSuccess: () => invalidateTimesheets(queryClient, timesheetId),
  });
}

// --- Time entries --------------------------------------------------------------

export function useTimeEntries(timesheetId: string | undefined) {
  return useQuery({
    queryKey: ["hr", "time-entries", timesheetId],
    queryFn: () => listTimeEntries(timesheetId as string),
    enabled: timesheetId !== undefined,
  });
}

export function useAddTimeEntry(timesheetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: TimeEntryCreate) => addTimeEntry(timesheetId, payload),
    onSuccess: () => invalidateTimesheets(queryClient, timesheetId),
  });
}

export function useRemoveTimeEntry(timesheetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (entryId: string) => removeTimeEntry(timesheetId, entryId),
    onSuccess: () => invalidateTimesheets(queryClient, timesheetId),
  });
}

// --- Allocation report ----------------------------------------------------------

export function useTimeAllocation(
  by: AllocationDimension,
  dateFrom: string | undefined,
  dateTo: string | undefined,
) {
  return useQuery({
    queryKey: ["hr", "time-allocation", by, dateFrom, dateTo],
    queryFn: () => getTimeAllocation(by, dateFrom as string, dateTo as string),
    enabled: dateFrom !== undefined && dateTo !== undefined,
  });
}
