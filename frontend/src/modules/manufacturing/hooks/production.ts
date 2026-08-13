/**
 * Production-order hooks (STRUCTURE §4). Every lifecycle action returns the full refreshed
 * detail, so mutations invalidate both the list and the one detail key.
 */

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelProductionOrder,
  createProductionOrder,
  finishProductionOrder,
  getProductionOrder,
  issueComponents,
  listProductionOrders,
  releaseProductionOrder,
  type ProductionOrderFilters,
} from "@/modules/manufacturing/api";
import type {
  FinishOrderRequest,
  IssueComponentsRequest,
  ProductionOrderCreate,
} from "@/modules/manufacturing/types";

export function useProductionOrders(filters: Omit<ProductionOrderFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["manufacturing", "production-orders", filters],
    queryFn: ({ pageParam }) =>
      listProductionOrders({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useProductionOrder(orderId: string | undefined) {
  return useQuery({
    queryKey: ["manufacturing", "production-order", orderId],
    queryFn: () => getProductionOrder(orderId as string),
    enabled: orderId !== undefined,
  });
}

function invalidateOrder(queryClient: ReturnType<typeof useQueryClient>, orderId: string) {
  void queryClient.invalidateQueries({ queryKey: ["manufacturing", "production-orders"] });
  void queryClient.invalidateQueries({ queryKey: ["manufacturing", "production-order", orderId] });
}

export function useCreateProductionOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProductionOrderCreate) => createProductionOrder(payload),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["manufacturing", "production-orders"] }),
  });
}

export function useReleaseProductionOrder(orderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => releaseProductionOrder(orderId),
    onSuccess: () => invalidateOrder(queryClient, orderId),
  });
}

export function useIssueComponents(orderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: IssueComponentsRequest) => issueComponents(orderId, payload),
    onSuccess: () => invalidateOrder(queryClient, orderId),
  });
}

export function useFinishProductionOrder(orderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: FinishOrderRequest) => finishProductionOrder(orderId, payload),
    onSuccess: () => invalidateOrder(queryClient, orderId),
  });
}

export function useCancelProductionOrder(orderId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelProductionOrder(orderId),
    onSuccess: () => invalidateOrder(queryClient, orderId),
  });
}
