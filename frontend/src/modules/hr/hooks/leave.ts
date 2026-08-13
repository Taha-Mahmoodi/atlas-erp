/**
 * TanStack Query hooks for leave (PLAN 10.2): leave types, per-employee accrual balances, the
 * accrual run, and leave requests with the submit/approve/reject/cancel flow. An APPROVED
 * request's cancel RESTORES the balance (D-053), so every request transition invalidates the
 * balances too.
 */

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  approveLeaveRequest,
  cancelLeaveRequest,
  createLeaveRequest,
  createLeaveType,
  getLeaveRequest,
  getLeaveType,
  type LeaveRequestFilters,
  type LeaveTypeFilters,
  listEmployeeLeaveBalances,
  listLeaveRequests,
  listLeaveTypes,
  rejectLeaveRequest,
  runLeaveAccrual,
  submitLeaveRequest,
  updateLeaveRequest,
  updateLeaveType,
} from "@/modules/hr/api";
import type {
  AccrualFrequency,
  LeaveDecision,
  LeaveRequestCreate,
  LeaveRequestUpdate,
  LeaveTypeCreate,
  LeaveTypeUpdate,
} from "@/modules/hr/types";

// --- Leave types ---------------------------------------------------------------

export function useLeaveTypes(filters: Omit<LeaveTypeFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["hr", "leave-types", filters],
    queryFn: ({ pageParam }) => listLeaveTypes({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

/** All leave types for pickers + label lookups (request form, balances table). */
export function useLeaveTypeOptions() {
  return useQuery({
    queryKey: ["hr", "leave-types", "options"],
    queryFn: () => listLeaveTypes({ limit: 200 }),
    staleTime: 60_000,
  });
}

export function useLeaveType(leaveTypeId: string | undefined) {
  return useQuery({
    queryKey: ["hr", "leave-type", leaveTypeId],
    queryFn: () => getLeaveType(leaveTypeId as string),
    enabled: leaveTypeId !== undefined,
  });
}

function invalidateLeaveTypes(queryClient: ReturnType<typeof useQueryClient>, leaveTypeId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["hr", "leave-types"] });
  if (leaveTypeId) void queryClient.invalidateQueries({ queryKey: ["hr", "leave-type", leaveTypeId] });
}

export function useCreateLeaveType() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: LeaveTypeCreate) => createLeaveType(payload),
    onSuccess: () => invalidateLeaveTypes(queryClient),
  });
}

export function useUpdateLeaveType(leaveTypeId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: LeaveTypeUpdate) => updateLeaveType(leaveTypeId, payload),
    onSuccess: () => invalidateLeaveTypes(queryClient, leaveTypeId),
  });
}

// --- Balances + the accrual run -------------------------------------------------

export function useEmployeeLeaveBalances(employeeId: string | undefined) {
  return useQuery({
    queryKey: ["hr", "leave-balances", employeeId],
    queryFn: () => listEmployeeLeaveBalances(employeeId as string),
    enabled: employeeId !== undefined,
  });
}

export function useRunLeaveAccrual() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ frequency, asOf }: { frequency: AccrualFrequency; asOf?: string }) =>
      runLeaveAccrual(frequency, asOf),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["hr", "leave-balances"] }),
  });
}

// --- Leave requests ------------------------------------------------------------

export function useLeaveRequests(filters: Omit<LeaveRequestFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["hr", "leave-requests", filters],
    queryFn: ({ pageParam }) => listLeaveRequests({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useLeaveRequest(requestId: string | undefined) {
  return useQuery({
    queryKey: ["hr", "leave-request", requestId],
    queryFn: () => getLeaveRequest(requestId as string),
    enabled: requestId !== undefined,
  });
}

function invalidateLeaveRequests(queryClient: ReturnType<typeof useQueryClient>, requestId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["hr", "leave-requests"] });
  if (requestId) void queryClient.invalidateQueries({ queryKey: ["hr", "leave-request", requestId] });
  void queryClient.invalidateQueries({ queryKey: ["hr", "leave-balances"] });
}

export function useCreateLeaveRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: LeaveRequestCreate) => createLeaveRequest(payload),
    onSuccess: () => invalidateLeaveRequests(queryClient),
  });
}

export function useUpdateLeaveRequest(requestId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: LeaveRequestUpdate) => updateLeaveRequest(requestId, payload),
    onSuccess: () => invalidateLeaveRequests(queryClient, requestId),
  });
}

export function useSubmitLeaveRequest(requestId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => submitLeaveRequest(requestId),
    onSuccess: () => invalidateLeaveRequests(queryClient, requestId),
  });
}

export function useApproveLeaveRequest(requestId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: LeaveDecision) => approveLeaveRequest(requestId, payload),
    onSuccess: () => invalidateLeaveRequests(queryClient, requestId),
  });
}

export function useRejectLeaveRequest(requestId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: LeaveDecision) => rejectLeaveRequest(requestId, payload),
    onSuccess: () => invalidateLeaveRequests(queryClient, requestId),
  });
}

export function useCancelLeaveRequest(requestId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelLeaveRequest(requestId),
    onSuccess: () => invalidateLeaveRequests(queryClient, requestId),
  });
}
