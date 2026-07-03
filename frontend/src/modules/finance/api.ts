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
  EntryStatus,
  JournalEntry,
  JournalEntryCreate,
  JournalEntryDetail,
  JournalEntryReverseRequest,
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
