import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createVendorBill,
  createVendorPayment,
  getApAging,
  getVendorBill,
  listVendorBills,
  listVendorPayments,
  postVendorBill,
  type VendorBillFilters,
  type VendorPaymentFilters,
} from "@/modules/finance/api";
import type { VendorBillCreate, VendorPaymentCreate } from "@/modules/finance/types";

export function useVendorBills(filters: Omit<VendorBillFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["finance", "vendor-bills", filters],
    queryFn: ({ pageParam }) =>
      listVendorBills({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useVendorBill(billId: string | undefined) {
  return useQuery({
    queryKey: ["finance", "vendor-bill", billId],
    queryFn: () => getVendorBill(billId as string),
    enabled: billId !== undefined,
  });
}

/** Every open (POSTED / PARTIALLY_PAID) bill for one vendor — the payment form's allocation
 * picker. Not infinite: a vendor's open-bill count is small enough for one page in v1. */
export function useOpenVendorBills(partnerId: string | undefined) {
  return useQuery({
    queryKey: ["finance", "vendor-bills", "open", partnerId],
    queryFn: () => listVendorBills({ partner_id: partnerId as string, limit: 100 }),
    enabled: partnerId !== undefined,
    select: (page) =>
      page.items.filter(
        (bill) => bill.status === "POSTED" || bill.status === "PARTIALLY_PAID",
      ),
  });
}

export function useCreateVendorBill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: VendorBillCreate) => createVendorBill(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "vendor-bills"] });
    },
  });
}

export function usePostVendorBill(billId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => postVendorBill(billId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "vendor-bills"] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "vendor-bill", billId] });
    },
  });
}

export function useCreateVendorPayment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: VendorPaymentCreate) => createVendorPayment(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "vendor-bills"] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "vendor-payments"] });
    },
  });
}

export function useVendorPayments(filters: Omit<VendorPaymentFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["finance", "vendor-payments", filters],
    queryFn: ({ pageParam }) =>
      listVendorPayments({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useApAging(asOf: string, partnerId?: string) {
  return useQuery({
    queryKey: ["finance", "ap-aging", asOf, partnerId],
    queryFn: () => getApAging(asOf, partnerId),
  });
}
