import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type AccountFilters,
  createAccount,
  createJournalEntry,
  getAccount,
  getJournalEntry,
  type JournalEntryFilters,
  listAccountGroups,
  listAccounts,
  listJournalEntries,
  postJournalEntry,
  reverseJournalEntry,
  updateAccount,
} from "@/modules/finance/api";
import type {
  AccountCreate,
  AccountUpdate,
  JournalEntryCreate,
  JournalEntryReverseRequest,
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
