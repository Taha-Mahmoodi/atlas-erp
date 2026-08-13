import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelRequisition,
  convertRequisitionToPurchaseOrder,
  convertRequisitionToRfq,
  createRequisition,
  decideRequisition,
  getRequisition,
  listRequisitions,
  type RequisitionFilters,
  submitRequisition,
  updateRequisition,
} from "@/modules/procurement/api";
import type {
  ApprovalDecisionPayload,
  PurchaseOrderFromRequisition,
  RequisitionCreate,
  RequisitionUpdate,
  RfqFromRequisition,
} from "@/modules/procurement/types";

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

export function useConvertRequisitionToRfq(requisitionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RfqFromRequisition) => convertRequisitionToRfq(requisitionId, payload),
    onSuccess: () => {
      invalidateRequisition(queryClient, requisitionId);
      void queryClient.invalidateQueries({ queryKey: ["procurement", "rfqs"] });
    },
  });
}

export function useConvertRequisitionToPurchaseOrder(requisitionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PurchaseOrderFromRequisition) =>
      convertRequisitionToPurchaseOrder(requisitionId, payload),
    onSuccess: () => {
      invalidateRequisition(queryClient, requisitionId);
      void queryClient.invalidateQueries({ queryKey: ["procurement", "purchase-orders"] });
    },
  });
}
