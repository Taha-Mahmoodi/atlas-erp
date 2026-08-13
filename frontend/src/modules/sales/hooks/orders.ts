import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelSalesOrder,
  checkAtp,
  confirmSalesOrder,
  createSalesOrder,
  getSalesOrder,
  listSalesOrders,
  releaseSalesOrderCredit,
  type SalesOrderFilters,
  updateSalesOrder,
} from "@/modules/sales/api";
import type { AtpCheckRequest, SalesOrderCreate, SalesOrderUpdate } from "@/modules/sales/types";

export function useSalesOrders(filters: Omit<SalesOrderFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["sales", "orders", filters],
    queryFn: ({ pageParam }) => listSalesOrders({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useSalesOrder(orderId: string | undefined) {
  return useQuery({
    queryKey: ["sales", "order", orderId],
    queryFn: () => getSalesOrder(orderId as string),
    enabled: orderId !== undefined,
  });
}

function invalidateSalesOrder(queryClient: ReturnType<typeof useQueryClient>, orderId: string) {
  void queryClient.invalidateQueries({ queryKey: ["sales", "orders"] });
  void queryClient.invalidateQueries({ queryKey: ["sales", "order", orderId] });
}

export function useCreateSalesOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SalesOrderCreate) => createSalesOrder(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["sales", "orders"] }),
  });
}

export function useUpdateSalesOrder(orderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SalesOrderUpdate) => updateSalesOrder(orderId, payload),
    onSuccess: () => invalidateSalesOrder(queryClient, orderId),
  });
}

export function useCancelSalesOrder(orderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelSalesOrder(orderId),
    onSuccess: () => invalidateSalesOrder(queryClient, orderId),
  });
}

export function useConfirmSalesOrder(orderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => confirmSalesOrder(orderId),
    onSuccess: () => invalidateSalesOrder(queryClient, orderId),
  });
}

export function useReleaseSalesOrderCredit(orderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => releaseSalesOrderCredit(orderId),
    onSuccess: () => invalidateSalesOrder(queryClient, orderId),
  });
}

/** On-demand ATP preview for order-entry lines — a mutation, not a query, since it's triggered
 * by an explicit "check availability" action rather than kept in sync with reactive params. */
export function useCheckAtp() {
  return useMutation({
    mutationFn: (payload: AtpCheckRequest) => checkAtp(payload),
  });
}
