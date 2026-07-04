import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelDelivery,
  createDelivery,
  type DeliveryFilters,
  getDelivery,
  listDeliveries,
  postDelivery,
} from "@/modules/sales/api";
import type { DeliveryCreate } from "@/modules/sales/types";

export function useDeliveries(filters: Omit<DeliveryFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["sales", "deliveries", filters],
    queryFn: ({ pageParam }) => listDeliveries({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useDelivery(deliveryId: string | undefined) {
  return useQuery({
    queryKey: ["sales", "delivery", deliveryId],
    queryFn: () => getDelivery(deliveryId as string),
    enabled: deliveryId !== undefined,
  });
}

function invalidateDelivery(queryClient: ReturnType<typeof useQueryClient>, deliveryId: string) {
  void queryClient.invalidateQueries({ queryKey: ["sales", "deliveries"] });
  void queryClient.invalidateQueries({ queryKey: ["sales", "delivery", deliveryId] });
}

export function useCreateDelivery() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: DeliveryCreate) => createDelivery(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["sales", "deliveries"] }),
  });
}

export function usePostDelivery(deliveryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => postDelivery(deliveryId),
    onSuccess: () => {
      invalidateDelivery(queryClient, deliveryId);
      void queryClient.invalidateQueries({ queryKey: ["sales", "orders"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory"] });
    },
  });
}

export function useCancelDelivery(deliveryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelDelivery(deliveryId),
    onSuccess: () => invalidateDelivery(queryClient, deliveryId),
  });
}
