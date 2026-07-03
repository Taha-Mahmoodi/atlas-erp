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
 * so callers that format money need to look it up here. */
export function useFunctionalCurrency() {
  return useQuery({
    queryKey: ["finance", "currencies", "functional"],
    queryFn: () => listCurrencies(),
    staleTime: 5 * 60_000,
    select: (page) => page.items.find((currency) => currency.is_functional)?.code ?? "—",
  });
}
