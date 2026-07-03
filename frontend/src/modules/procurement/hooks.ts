import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type ApprovalRuleFilters,
  cancelRequisition,
  createApprovalRule,
  createRequisition,
  createVendor,
  createVendorApprovedItem,
  decideRequisition,
  deleteVendorApprovedItem,
  getApprovalRule,
  getRequisition,
  getVendor,
  listApprovalRules,
  listRequisitions,
  listVendorApprovedItems,
  listVendors,
  type RequisitionFilters,
  submitRequisition,
  updateApprovalRule,
  updateRequisition,
  updateVendor,
  type VendorFilters,
} from "@/modules/procurement/api";
import type {
  ApprovalDecisionPayload,
  ApprovalRuleCreate,
  ApprovalRuleUpdate,
  RequisitionCreate,
  RequisitionUpdate,
  VendorApprovedItemCreate,
  VendorCreate,
  VendorUpdate,
} from "@/modules/procurement/types";

export function useVendors(filters: Omit<VendorFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["procurement", "vendors", filters],
    queryFn: ({ pageParam }) =>
      listVendors({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useVendor(vendorId: string | undefined) {
  return useQuery({
    queryKey: ["procurement", "vendor", vendorId],
    queryFn: () => getVendor(vendorId as string),
    enabled: vendorId !== undefined,
  });
}

/** All active vendors for a picker (a plain select, not paginated — mirrors finance's
 * useAccountOptions; a searchable combobox is worth adding once a vendor list outgrows one
 * page). Kept under this same name for the finance AP workbench, which already depends on it. */
export function useVendorOptions() {
  return useQuery({
    queryKey: ["procurement", "vendors", "options"],
    queryFn: () => listVendors({ status: "ACTIVE", limit: 200 }),
    staleTime: 60_000,
  });
}

/** Every vendor (no filters) for resolving vendor_id -> code/name on read-only views — a
 * posted document may reference a since-blocked/deactivated vendor. */
export function useVendorLookup() {
  return useQuery({
    queryKey: ["procurement", "vendors", "lookup"],
    queryFn: () => listVendors({ limit: 200 }),
    staleTime: 60_000,
  });
}

export function useCreateVendor() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: VendorCreate) => createVendor(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["procurement", "vendors"] });
    },
  });
}

export function useUpdateVendor(vendorId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: VendorUpdate) => updateVendor(vendorId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["procurement", "vendors"] });
      void queryClient.invalidateQueries({ queryKey: ["procurement", "vendor", vendorId] });
    },
  });
}

export function useVendorApprovedItems(vendorId: string | undefined) {
  return useQuery({
    queryKey: ["procurement", "vendor-approved-items", vendorId],
    queryFn: () => listVendorApprovedItems(vendorId as string),
    enabled: vendorId !== undefined,
  });
}

export function useCreateVendorApprovedItem(vendorId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: VendorApprovedItemCreate) => createVendorApprovedItem(vendorId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["procurement", "vendor-approved-items", vendorId] });
    },
  });
}

export function useDeleteVendorApprovedItem(vendorId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => deleteVendorApprovedItem(vendorId, itemId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["procurement", "vendor-approved-items", vendorId] });
    },
  });
}

// --- Approval rules ------------------------------------------------------------

export function useApprovalRules(filters: Omit<ApprovalRuleFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["procurement", "approval-rules", filters],
    queryFn: ({ pageParam }) =>
      listApprovalRules({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useApprovalRule(ruleId: string | undefined) {
  return useQuery({
    queryKey: ["procurement", "approval-rule", ruleId],
    queryFn: () => getApprovalRule(ruleId as string),
    enabled: ruleId !== undefined,
  });
}

export function useCreateApprovalRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApprovalRuleCreate) => createApprovalRule(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["procurement", "approval-rules"] });
    },
  });
}

export function useUpdateApprovalRule(ruleId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApprovalRuleUpdate) => updateApprovalRule(ruleId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["procurement", "approval-rules"] });
      void queryClient.invalidateQueries({ queryKey: ["procurement", "approval-rule", ruleId] });
    },
  });
}

// --- Purchase requisitions -------------------------------------------------------

export function useRequisitions(filters: Omit<RequisitionFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["procurement", "requisitions", filters],
    queryFn: ({ pageParam }) =>
      listRequisitions({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useRequisition(requisitionId: string | undefined) {
  return useQuery({
    queryKey: ["procurement", "requisition", requisitionId],
    queryFn: () => getRequisition(requisitionId as string),
    enabled: requisitionId !== undefined,
  });
}

function invalidateRequisition(queryClient: ReturnType<typeof useQueryClient>, requisitionId: string) {
  void queryClient.invalidateQueries({ queryKey: ["procurement", "requisitions"] });
  void queryClient.invalidateQueries({ queryKey: ["procurement", "requisition", requisitionId] });
}

export function useCreateRequisition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RequisitionCreate) => createRequisition(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["procurement", "requisitions"] });
    },
  });
}

export function useUpdateRequisition(requisitionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RequisitionUpdate) => updateRequisition(requisitionId, payload),
    onSuccess: () => invalidateRequisition(queryClient, requisitionId),
  });
}

export function useSubmitRequisition(requisitionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => submitRequisition(requisitionId),
    onSuccess: () => invalidateRequisition(queryClient, requisitionId),
  });
}

export function useDecideRequisition(requisitionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApprovalDecisionPayload) => decideRequisition(requisitionId, payload),
    onSuccess: () => invalidateRequisition(queryClient, requisitionId),
  });
}

export function useCancelRequisition(requisitionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelRequisition(requisitionId),
    onSuccess: () => invalidateRequisition(queryClient, requisitionId),
  });
}
