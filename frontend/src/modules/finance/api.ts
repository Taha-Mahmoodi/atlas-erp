/**
 * Typed endpoint calls for the finance module only (STRUCTURE §4): chart of accounts +
 * account groups + journal entries. AP/AR/statements/bank-rec/assets land in later slices
 * of PLAN 15.4.
 */

import { api, newIdempotencyKey, type Page } from "@/lib/apiClient";
import type {
  Account,
  AccountCreate,
  AccountGroup,
  AccountType,
  AccountUpdate,
  AgingReport,
  BillStatus,
  EntryStatus,
  JournalEntry,
  JournalEntryCreate,
  JournalEntryDetail,
  JournalEntryReverseRequest,
  TaxCode,
  VendorBill,
  VendorBillCreate,
  VendorBillDetail,
  VendorPayment,
  VendorPaymentCreate,
  VendorPaymentDetail,
} from "@/modules/finance/types";

export interface AccountFilters {
  cursor?: string;
  limit?: number;
  account_type?: AccountType;
  is_postable?: boolean;
  is_active?: boolean;
  account_group_id?: string;
}

export function listAccounts(filters: AccountFilters = {}): Promise<Page<Account>> {
  return api.get<Page<Account>>("/finance/accounts", { params: { ...filters } });
}

export function getAccount(accountId: string): Promise<Account> {
  return api.get<Account>(`/finance/accounts/${accountId}`);
}

export function createAccount(payload: AccountCreate): Promise<Account> {
  return api.post<Account>("/finance/accounts", payload);
}

export function updateAccount(accountId: string, payload: AccountUpdate): Promise<Account> {
  return api.patch<Account>(`/finance/accounts/${accountId}`, payload);
}

export function listAccountGroups(): Promise<Page<AccountGroup>> {
  return api.get<Page<AccountGroup>>("/finance/account-groups", { params: { limit: 100 } });
}

export interface JournalEntryFilters {
  cursor?: string;
  limit?: number;
  status?: EntryStatus;
}

export function listJournalEntries(
  filters: JournalEntryFilters = {},
): Promise<Page<JournalEntry>> {
  return api.get<Page<JournalEntry>>("/finance/journal-entries", { params: { ...filters } });
}

export function getJournalEntry(entryId: string): Promise<JournalEntryDetail> {
  return api.get<JournalEntryDetail>(`/finance/journal-entries/${entryId}`);
}

export function createJournalEntry(payload: JournalEntryCreate): Promise<JournalEntry> {
  // Draft creation is deliberately NOT idempotency-gated on the backend (a duplicate draft
  // has zero GL effect until posted) — post/reverse below are.
  return api.post<JournalEntry>("/finance/journal-entries", payload);
}

export function postJournalEntry(entryId: string): Promise<JournalEntryDetail> {
  return api.post<JournalEntryDetail>(
    `/finance/journal-entries/${entryId}/post`,
    undefined,
    { idempotencyKey: newIdempotencyKey() },
  );
}

export function reverseJournalEntry(
  entryId: string,
  payload: JournalEntryReverseRequest,
): Promise<JournalEntryDetail> {
  return api.post<JournalEntryDetail>(
    `/finance/journal-entries/${entryId}/reverse`,
    payload,
    { idempotencyKey: newIdempotencyKey() },
  );
}

export function listTaxCodes(): Promise<Page<TaxCode>> {
  return api.get<Page<TaxCode>>("/finance/tax-codes", { params: { is_active: true, limit: 100 } });
}

// --- Accounts Payable ----------------------------------------------------------

export interface VendorBillFilters {
  cursor?: string;
  limit?: number;
  status?: BillStatus;
  partner_id?: string;
}

export function listVendorBills(filters: VendorBillFilters = {}): Promise<Page<VendorBill>> {
  return api.get<Page<VendorBill>>("/finance/vendor-bills", { params: { ...filters } });
}

export function getVendorBill(billId: string): Promise<VendorBillDetail> {
  return api.get<VendorBillDetail>(`/finance/vendor-bills/${billId}`);
}

export function createVendorBill(payload: VendorBillCreate): Promise<VendorBill> {
  return api.post<VendorBill>("/finance/vendor-bills", payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function postVendorBill(billId: string): Promise<VendorBillDetail> {
  return api.post<VendorBillDetail>(`/finance/vendor-bills/${billId}/post`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function createVendorPayment(payload: VendorPaymentCreate): Promise<VendorPaymentDetail> {
  return api.post<VendorPaymentDetail>("/finance/vendor-payments", payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export interface VendorPaymentFilters {
  cursor?: string;
  limit?: number;
  partner_id?: string;
}

export function listVendorPayments(
  filters: VendorPaymentFilters = {},
): Promise<Page<VendorPayment>> {
  return api.get<Page<VendorPayment>>("/finance/vendor-payments", { params: { ...filters } });
}

export function getApAging(asOf: string, partnerId?: string): Promise<AgingReport> {
  return api.get<AgingReport>("/finance/ap-aging", {
    params: { as_of: asOf, ...(partnerId ? { partner_id: partnerId } : {}) },
  });
}
