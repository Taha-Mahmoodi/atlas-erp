import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type AccountFilters,
  createAccount,
  getAccount,
  listAccountGroups,
  listAccounts,
  updateAccount,
} from "@/modules/finance/api";
import type { AccountCreate, AccountUpdate } from "@/modules/finance/types";

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

/** Postable, active, cash-equivalent accounts — the bank-account picker for statement
 * import. A "bank account" has no separate model (bank_router.py's own definition); it's a
 * regular Account with is_cash_equivalent = true. No server-side filter for that flag, so
 * this narrows client-side over the same options query. */
export function useBankAccountOptions() {
  return useQuery({
    queryKey: ["finance", "accounts", "options"],
    queryFn: () => listAccounts({ is_postable: true, is_active: true, limit: 200 }),
    staleTime: 60_000,
    select: (page) => page.items.filter((account) => account.is_cash_equivalent),
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
