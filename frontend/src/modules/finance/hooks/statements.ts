import { useQuery } from "@tanstack/react-query";

import {
  getBalanceSheet,
  getCashFlowStatement,
  getProfitAndLoss,
  getTrialBalance,
} from "@/modules/finance/api";

export function useTrialBalance(asOf: string) {
  return useQuery({
    queryKey: ["finance", "trial-balance", asOf],
    queryFn: () => getTrialBalance(asOf),
  });
}

export function useProfitAndLoss(dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: ["finance", "profit-loss", dateFrom, dateTo],
    queryFn: () => getProfitAndLoss(dateFrom, dateTo),
  });
}

export function useBalanceSheet(asOf: string) {
  return useQuery({
    queryKey: ["finance", "balance-sheet", asOf],
    queryFn: () => getBalanceSheet(asOf),
  });
}

export function useCashFlowStatement(dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: ["finance", "cash-flow", dateFrom, dateTo],
    queryFn: () => getCashFlowStatement(dateFrom, dateTo),
  });
}
