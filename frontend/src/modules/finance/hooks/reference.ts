import { useQuery } from "@tanstack/react-query";

import { listCurrencies, listTaxCodes } from "@/modules/finance/api";

export function useTaxCodes() {
  return useQuery({
    queryKey: ["finance", "tax-codes"],
    queryFn: () => listTaxCodes(),
    staleTime: 5 * 60_000,
  });
}

/** The tenant's single functional currency (D-058's "—" sentinel covers the unconfigured
 * case) — statements report in this currency but don't echo the code in their own responses,
 * so callers that format money need to look it up here.
 *
 * `GET /currencies` is guarded by `finance.fx.manage` — an ADMIN permission — while this is a
 * money LABEL on 15 pages across 8 modules (a check, a stock valuation, a maintenance order).
 * Under the global throwOnError (lib/queryClient.ts) that mismatch replaced each of those pages
 * with a full-page 403 for every persona that cannot administer FX, and #180's rule is about the
 * record a page is FOR — which is the ticket, the count, the order, never the currency catalog.
 * So the 4xx stays inline and each caller's existing `?? "—"` does the degrading, showing exactly
 * what an unconfigured tenant already sees. `useCurrencyOptions` (hooks/settings.ts) reads the
 * same endpoint and KEEPS the default on purpose: on the exchange-rate form, and on that form
 * only, the currency list is the record the page is for. */
export function useFunctionalCurrency() {
  return useQuery({
    queryKey: ["finance", "currencies", "functional"],
    queryFn: () => listCurrencies(),
    staleTime: 5 * 60_000,
    select: (page) => page.items.find((currency) => currency.is_functional)?.code ?? "—",
    throwOnError: false,
  });
}
