import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type AccountFilters,
  createAccount,
  createCustomerInvoice,
  createCustomerReceipt,
  createJournalEntry,
  createVendorBill,
  createVendorPayment,
  type CustomerInvoiceFilters,
  type CustomerReceiptFilters,
  getAccount,
  getApAging,
  getArAging,
  getCustomerInvoice,
  getJournalEntry,
  getVendorBill,
  type JournalEntryFilters,
  listAccountGroups,
  listAccounts,
  listCustomerInvoices,
  listCustomerReceipts,
  listJournalEntries,
  listTaxCodes,
  listVendorBills,
  listVendorPayments,
  postCustomerInvoice,
  postJournalEntry,
  postVendorBill,
  reverseJournalEntry,
  runDunning,
  updateAccount,
  type VendorBillFilters,
  type VendorPaymentFilters,
} from "@/modules/finance/api";
import type {
  AccountCreate,
  AccountUpdate,
  CustomerInvoiceCreate,
  CustomerReceiptCreate,
  DunningRunRequest,
  JournalEntryCreate,
  JournalEntryReverseRequest,
  VendorBillCreate,
  VendorPaymentCreate,
} from "@/modules/finance/types";

/** Keyset-paginated (D-014) — pages accumulate via `fetchNextPage`, they don't replace. */
export function useAccounts(filters: Omit<AccountFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["finance", "accounts", filters],
    queryFn: ({ pageParam }) =>
      listAccounts({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useAccount(accountId: string | undefined) {
  return useQuery({
    queryKey: ["finance", "account", accountId],
    queryFn: () => getAccount(accountId as string),
    enabled: accountId !== undefined,
  });
}

/** All postable, active accounts for a picker (a plain select, not a paginated list — v1
 * keeps this to one page; a searchable combobox is worth adding once a chart outgrows it). */
export function useAccountOptions() {
  return useQuery({
    queryKey: ["finance", "accounts", "options"],
    queryFn: () => listAccounts({ is_postable: true, is_active: true, limit: 200 }),
    staleTime: 60_000,
  });
}

/** Every account (no filters) for resolving account_id -> code/name on read-only views —
 * a posted line may reference a non-postable or since-deactivated account. */
export function useAccountLookup() {
  return useQuery({
    queryKey: ["finance", "accounts", "lookup"],
    queryFn: () => listAccounts({ limit: 200 }),
    staleTime: 60_000,
  });
}

export function useAccountGroups() {
  return useQuery({
    queryKey: ["finance", "account-groups"],
    queryFn: () => listAccountGroups(),
    staleTime: 5 * 60_000, // reference data, rarely changes within a session
  });
}

export function useCreateAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AccountCreate) => createAccount(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "accounts"] });
    },
  });
}

export function useUpdateAccount(accountId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AccountUpdate) => updateAccount(accountId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "accounts"] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "account", accountId] });
    },
  });
}

/** Keyset-paginated (D-014) — pages accumulate via `fetchNextPage`, they don't replace. */
export function useJournalEntries(filters: Omit<JournalEntryFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["finance", "journal-entries", filters],
    queryFn: ({ pageParam }) =>
      listJournalEntries({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useJournalEntry(entryId: string | undefined) {
  return useQuery({
    queryKey: ["finance", "journal-entry", entryId],
    queryFn: () => getJournalEntry(entryId as string),
    enabled: entryId !== undefined,
  });
}

export function useCreateJournalEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: JournalEntryCreate) => createJournalEntry(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "journal-entries"] });
    },
  });
}

export function usePostJournalEntry(entryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => postJournalEntry(entryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "journal-entries"] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "journal-entry", entryId] });
    },
  });
}

export function useReverseJournalEntry(entryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: JournalEntryReverseRequest) => reverseJournalEntry(entryId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "journal-entries"] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "journal-entry", entryId] });
    },
  });
}

// --- Tax codes -------------------------------------------------------------

export function useTaxCodes() {
  return useQuery({
    queryKey: ["finance", "tax-codes"],
    queryFn: () => listTaxCodes(),
    staleTime: 5 * 60_000,
  });
}

// --- Accounts Payable --------------------------------------------------------

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

// --- Accounts Receivable -----------------------------------------------------

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
