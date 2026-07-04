import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelBilling,
  createBilling,
  getBilling,
  listBillings,
  postBilling,
  type BillingFilters,
} from "@/modules/sales/api";
import type { BillingCreate } from "@/modules/sales/types";

export function useBillings(filters: Omit<BillingFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["sales", "billings", filters],
    queryFn: ({ pageParam }) => listBillings({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useBilling(billingId: string | undefined) {
  return useQuery({
    queryKey: ["sales", "billing", billingId],
    queryFn: () => getBilling(billingId as string),
    enabled: billingId !== undefined,
  });
}

function invalidateBilling(queryClient: ReturnType<typeof useQueryClient>, billingId: string) {
  void queryClient.invalidateQueries({ queryKey: ["sales", "billings"] });
  void queryClient.invalidateQueries({ queryKey: ["sales", "billing", billingId] });
}

export function useCreateBilling() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BillingCreate) => createBilling(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["sales", "billings"] }),
  });
}

export function usePostBilling(billingId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => postBilling(billingId),
    onSuccess: () => {
      invalidateBilling(queryClient, billingId);
      void queryClient.invalidateQueries({ queryKey: ["sales", "orders"] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "customer-invoices"] });
    },
  });
}

export function useCancelBilling(billingId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelBilling(billingId),
    onSuccess: () => invalidateBilling(queryClient, billingId),
  });
}
