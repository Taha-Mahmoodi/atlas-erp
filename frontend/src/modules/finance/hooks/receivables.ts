import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createCustomerInvoice,
  createCustomerReceipt,
  type CustomerInvoiceFilters,
  type CustomerReceiptFilters,
  getArAging,
  getCustomerInvoice,
  listCustomerInvoices,
  listCustomerReceipts,
  postCustomerInvoice,
  runDunning,
} from "@/modules/finance/api";
import type {
  CustomerInvoiceCreate,
  CustomerReceiptCreate,
  DunningRunRequest,
} from "@/modules/finance/types";

export function useCustomerInvoices(filters: Omit<CustomerInvoiceFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["finance", "customer-invoices", filters],
    queryFn: ({ pageParam }) =>
      listCustomerInvoices({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useCustomerInvoice(invoiceId: string | undefined) {
  return useQuery({
    queryKey: ["finance", "customer-invoice", invoiceId],
    queryFn: () => getCustomerInvoice(invoiceId as string),
    enabled: invoiceId !== undefined,
  });
}

/** Every open (POSTED / PARTIALLY_PAID) invoice for one customer — the receipt form's
 * allocation picker. Mirrors useOpenVendorBills. */
export function useOpenCustomerInvoices(partnerId: string | undefined) {
  return useQuery({
    queryKey: ["finance", "customer-invoices", "open", partnerId],
    queryFn: () => listCustomerInvoices({ partner_id: partnerId as string, limit: 100 }),
    enabled: partnerId !== undefined,
    select: (page) =>
      page.items.filter(
        (invoice) => invoice.status === "POSTED" || invoice.status === "PARTIALLY_PAID",
      ),
  });
}

export function useCreateCustomerInvoice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CustomerInvoiceCreate) => createCustomerInvoice(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "customer-invoices"] });
    },
  });
}

export function usePostCustomerInvoice(invoiceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => postCustomerInvoice(invoiceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "customer-invoices"] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "customer-invoice", invoiceId] });
    },
  });
}

export function useCreateCustomerReceipt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CustomerReceiptCreate) => createCustomerReceipt(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "customer-invoices"] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "customer-receipts"] });
    },
  });
}

export function useCustomerReceipts(filters: Omit<CustomerReceiptFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["finance", "customer-receipts", filters],
    queryFn: ({ pageParam }) =>
      listCustomerReceipts({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useRunDunning() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: DunningRunRequest) => runDunning(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "customer-invoices"] });
    },
  });
}

export function useArAging(asOf: string, partnerId?: string) {
  return useQuery({
    queryKey: ["finance", "ar-aging", asOf, partnerId],
    queryFn: () => getArAging(asOf, partnerId),
  });
}
