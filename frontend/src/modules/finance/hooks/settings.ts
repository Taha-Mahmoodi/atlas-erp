/**
 * Hooks for the finance settings pages (PLAN 15.12): tax codes + exchange rates. Separate
 * from reference.ts, whose picker-shaped useTaxCodes (active-only, 100 rows, long stale
 * time) the bill/invoice forms depend on — these are the full paginated settings queries.
 */

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createExchangeRate,
  createTaxCode,
  getTaxCode,
  listCurrencies,
  listExchangeRates,
  listTaxCodesPage,
  updateTaxCode,
  type ExchangeRateFilters,
} from "@/modules/finance/api";
import type { ExchangeRateCreate, TaxCodeCreate, TaxCodeUpdate } from "@/modules/finance/types";

// --- Tax codes ------------------------------------------------------------------

export function useTaxCodesPage() {
  return useInfiniteQuery({
    queryKey: ["finance", "tax-codes", "settings"],
    queryFn: ({ pageParam }) => listTaxCodesPage(pageParam ? { cursor: pageParam } : {}),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useTaxCode(taxCodeId: string | undefined) {
  return useQuery({
    queryKey: ["finance", "tax-code", taxCodeId],
    queryFn: () => getTaxCode(taxCodeId as string),
    enabled: taxCodeId !== undefined,
  });
}

/** Invalidates BOTH the settings list and reference.ts's picker cache on any write. */
function useInvalidateTaxCodes() {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: ["finance", "tax-codes"] });
}

export function useCreateTaxCode() {
  const invalidate = useInvalidateTaxCodes();
  return useMutation({
    mutationFn: (payload: TaxCodeCreate) => createTaxCode(payload),
    onSuccess: invalidate,
  });
}

export function useUpdateTaxCode(taxCodeId: string) {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateTaxCodes();
  return useMutation({
    mutationFn: (payload: TaxCodeUpdate) => updateTaxCode(taxCodeId, payload),
    onSuccess: () => {
      invalidate();
      void queryClient.invalidateQueries({ queryKey: ["finance", "tax-code", taxCodeId] });
    },
  });
}

// --- Exchange rates -------------------------------------------------------------

export function useExchangeRates(filters: Omit<ExchangeRateFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["finance", "exchange-rates", filters],
    queryFn: ({ pageParam }) =>
      listExchangeRates({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useCreateExchangeRate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ExchangeRateCreate) => createExchangeRate(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["finance", "exchange-rates"] });
    },
  });
}

/** All tenant currencies for the rate form's from/to pickers (one 100-row page). */
export function useCurrencyOptions() {
  return useQuery({
    queryKey: ["finance", "currencies", "options"],
    queryFn: () => listCurrencies(),
    staleTime: 5 * 60_000,
  });
}
