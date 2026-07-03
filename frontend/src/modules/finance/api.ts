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
  BalanceSheet,
  BillStatus,
  CashFlowStatement,
  Currency,
  CustomerInvoice,
  CustomerInvoiceCreate,
  CustomerInvoiceDetail,
  CustomerReceipt,
  CustomerReceiptCreate,
  CustomerReceiptDetail,
  DunningRunRequest,
  DunningRunResult,
  EntryStatus,
  InvoiceStatus,
  JournalEntry,
  JournalEntryCreate,
  JournalEntryDetail,
  JournalEntryReverseRequest,
  ProfitAndLoss,
  TaxCode,
  TrialBalance,
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

export function listCurrencies(): Promise<Page<Currency>> {
  return api.get<Page<Currency>>("/finance/currencies", { params: { limit: 100 } });
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

// --- Accounts Receivable ---------------------------------------------------

export interface CustomerInvoiceFilters {
  cursor?: string;
  limit?: number;
  status?: InvoiceStatus;
  partner_id?: string;
}

export function listCustomerInvoices(
  filters: CustomerInvoiceFilters = {},
): Promise<Page<CustomerInvoice>> {
  return api.get<Page<CustomerInvoice>>("/finance/customer-invoices", { params: { ...filters } });
}

export function getCustomerInvoice(invoiceId: string): Promise<CustomerInvoiceDetail> {
  return api.get<CustomerInvoiceDetail>(`/finance/customer-invoices/${invoiceId}`);
}

export function createCustomerInvoice(payload: CustomerInvoiceCreate): Promise<CustomerInvoice> {
  return api.post<CustomerInvoice>("/finance/customer-invoices", payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function postCustomerInvoice(invoiceId: string): Promise<CustomerInvoiceDetail> {
  return api.post<CustomerInvoiceDetail>(`/finance/customer-invoices/${invoiceId}/post`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function createCustomerReceipt(
  payload: CustomerReceiptCreate,
): Promise<CustomerReceiptDetail> {
  return api.post<CustomerReceiptDetail>("/finance/customer-receipts", payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export interface CustomerReceiptFilters {
  cursor?: string;
  limit?: number;
  partner_id?: string;
}

export function listCustomerReceipts(
  filters: CustomerReceiptFilters = {},
): Promise<Page<CustomerReceipt>> {
  return api.get<Page<CustomerReceipt>>("/finance/customer-receipts", { params: { ...filters } });
}

export function runDunning(payload: DunningRunRequest): Promise<DunningRunResult> {
  return api.post<DunningRunResult>("/finance/dunning-runs", payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function getArAging(asOf: string, partnerId?: string): Promise<AgingReport> {
  return api.get<AgingReport>("/finance/ar-aging", {
    params: { as_of: asOf, ...(partnerId ? { partner_id: partnerId } : {}) },
  });
}

// --- Financial statements ---------------------------------------------------
// Plain synchronous reads (no writes, no idempotency, no job/polling) — a single full object
// each, not Page<T>. No server-side comparison-period support: two calls + client-side diff.

export function getTrialBalance(asOf: string): Promise<TrialBalance> {
  return api.get<TrialBalance>("/finance/statements/trial-balance", { params: { as_of: asOf } });
}

export function getProfitAndLoss(dateFrom: string, dateTo: string): Promise<ProfitAndLoss> {
  return api.get<ProfitAndLoss>("/finance/statements/profit-loss", {
    params: { date_from: dateFrom, date_to: dateTo },
  });
}

export function getBalanceSheet(asOf: string): Promise<BalanceSheet> {
  return api.get<BalanceSheet>("/finance/statements/balance-sheet", { params: { as_of: asOf } });
}

export function getCashFlowStatement(dateFrom: string, dateTo: string): Promise<CashFlowStatement> {
  return api.get<CashFlowStatement>("/finance/statements/cash-flow", {
    params: { date_from: dateFrom, date_to: dateTo },
  });
}
