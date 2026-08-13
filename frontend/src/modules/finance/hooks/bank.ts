import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type BankStatementFilters,
  clearLine,
  confirmMatch,
  getBankStatement,
  importBankStatement,
  listBankStatementLines,
  listBankStatements,
  rejectSuggestion,
  suggestMatches,
} from "@/modules/finance/api";
import type {
  BankStatementImportRequest,
  ClearLineRequest,
} from "@/modules/finance/types";

export function useBankStatements(filters: Omit<BankStatementFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["finance", "bank-statements", filters],
    queryFn: ({ pageParam }) =>
      listBankStatements({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useBankStatement(statementId: string | undefined) {
  return useQuery({
    queryKey: ["finance", "bank-statement", statementId],
    queryFn: () => getBankStatement(statementId as string),
    enabled: statementId !== undefined,
  });
}

/** All lines for a statement, one page — a single bank statement's line count is bounded by
 * the sync-import cap (1000), so pagination isn't needed for the reconciliation workbench. */
export function useBankStatementLines(statementId: string | undefined) {
  return useQuery({
    queryKey: ["finance", "bank-statement-lines", statementId],
    queryFn: () => listBankStatementLines(statementId as string, { limit: 1000 }),
    enabled: statementId !== undefined,
  });
}

/** Returns the raw create response (BankStatement | JobSubmitted) — the caller (the import
 * page) distinguishes by checking for `job_id` and polls lib/jobs.ts if it's a job. */
export function useImportBankStatement() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BankStatementImportRequest) => importBankStatement(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "bank-statements"] });
    },
  });
}

export function useSuggestMatches(statementId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => suggestMatches(statementId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "bank-statement", statementId] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "bank-statement-lines", statementId] });
    },
  });
}

export function useConfirmMatch(statementId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (lineId: string) => confirmMatch(lineId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "bank-statement", statementId] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "bank-statement-lines", statementId] });
    },
  });
}

export function useRejectSuggestion(statementId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (lineId: string) => rejectSuggestion(lineId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "bank-statement", statementId] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "bank-statement-lines", statementId] });
    },
  });
}

export function useClearLine(statementId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ lineId, payload }: { lineId: string; payload?: ClearLineRequest }) =>
      clearLine(lineId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "bank-statement", statementId] });
      void queryClient.invalidateQueries({ queryKey: ["finance", "bank-statement-lines", statementId] });
    },
  });
}
