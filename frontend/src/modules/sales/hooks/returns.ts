import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelReturn,
  createReturn,
  getReturn,
  listReturns,
  postReturn,
  type ReturnFilters,
} from "@/modules/sales/api";
import type { ReturnCreate } from "@/modules/sales/types";

export function useReturns(filters: Omit<ReturnFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["sales", "returns", filters],
    queryFn: ({ pageParam }) => listReturns({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useReturn(returnId: string | undefined) {
  return useQuery({
    queryKey: ["sales", "return", returnId],
    queryFn: () => getReturn(returnId as string),
    enabled: returnId !== undefined,
  });
}

function invalidateReturn(queryClient: ReturnType<typeof useQueryClient>, returnId: string) {
  void queryClient.invalidateQueries({ queryKey: ["sales", "returns"] });
  void queryClient.invalidateQueries({ queryKey: ["sales", "return", returnId] });
}

export function useCreateReturn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ReturnCreate) => createReturn(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["sales", "returns"] }),
  });
}

export function usePostReturn(returnId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => postReturn(returnId),
    onSuccess: () => {
      invalidateReturn(queryClient, returnId);
      void queryClient.invalidateQueries({ queryKey: ["sales", "orders"] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "customer-invoices"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory"] });
    },
  });
}

export function useCancelReturn(returnId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelReturn(returnId),
    onSuccess: () => invalidateReturn(queryClient, returnId),
  });
}
