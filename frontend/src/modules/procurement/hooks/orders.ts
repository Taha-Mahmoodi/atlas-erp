import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelPurchaseOrder,
  createPurchaseOrder,
  decidePurchaseOrder,
  getPurchaseOrder,
  listPurchaseOrders,
  type PurchaseOrderFilters,
  sendPurchaseOrder,
} from "@/modules/procurement/api";
import type { ApprovalDecisionPayload, PurchaseOrderCreate } from "@/modules/procurement/types";

export function usePurchaseOrders(filters: Omit<PurchaseOrderFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["procurement", "purchase-orders", filters],
    queryFn: ({ pageParam }) =>
      listPurchaseOrders({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function usePurchaseOrder(purchaseOrderId: string | undefined) {
  return useQuery({
    queryKey: ["procurement", "purchase-order", purchaseOrderId],
    queryFn: () => getPurchaseOrder(purchaseOrderId as string),
    enabled: purchaseOrderId !== undefined,
  });
}

function invalidatePurchaseOrder(queryClient: ReturnType<typeof useQueryClient>, purchaseOrderId: string) {
  void queryClient.invalidateQueries({ queryKey: ["procurement", "purchase-orders"] });
  void queryClient.invalidateQueries({ queryKey: ["procurement", "purchase-order", purchaseOrderId] });
}

export function useCreatePurchaseOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PurchaseOrderCreate) => createPurchaseOrder(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["procurement", "purchase-orders"] });
    },
  });
}

export function useSendPurchaseOrder(purchaseOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => sendPurchaseOrder(purchaseOrderId),
    onSuccess: () => invalidatePurchaseOrder(queryClient, purchaseOrderId),
  });
}

export function useDecidePurchaseOrder(purchaseOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApprovalDecisionPayload) => decidePurchaseOrder(purchaseOrderId, payload),
    onSuccess: () => invalidatePurchaseOrder(queryClient, purchaseOrderId),
  });
}

export function useCancelPurchaseOrder(purchaseOrderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelPurchaseOrder(purchaseOrderId),
    onSuccess: () => invalidatePurchaseOrder(queryClient, purchaseOrderId),
  });
}
