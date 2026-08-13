import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  acceptQuote,
  cancelQuote,
  convertQuoteToOrder,
  createQuote,
  getQuote,
  listQuotes,
  type QuoteFilters,
  rejectQuote,
  sendQuote,
  updateQuote,
} from "@/modules/sales/api";
import type { ConvertQuoteToOrder, QuoteCreate, QuoteUpdate } from "@/modules/sales/types";

export function useQuotes(filters: Omit<QuoteFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["sales", "quotes", filters],
    queryFn: ({ pageParam }) => listQuotes({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useQuote(quoteId: string | undefined) {
  return useQuery({
    queryKey: ["sales", "quote", quoteId],
    queryFn: () => getQuote(quoteId as string),
    enabled: quoteId !== undefined,
  });
}

function invalidateQuote(queryClient: ReturnType<typeof useQueryClient>, quoteId: string) {
  void queryClient.invalidateQueries({ queryKey: ["sales", "quotes"] });
  void queryClient.invalidateQueries({ queryKey: ["sales", "quote", quoteId] });
}

export function useCreateQuote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: QuoteCreate) => createQuote(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["sales", "quotes"] }),
  });
}

export function useUpdateQuote(quoteId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: QuoteUpdate) => updateQuote(quoteId, payload),
    onSuccess: () => invalidateQuote(queryClient, quoteId),
  });
}

export function useSendQuote(quoteId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => sendQuote(quoteId),
    onSuccess: () => invalidateQuote(queryClient, quoteId),
  });
}

export function useAcceptQuote(quoteId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => acceptQuote(quoteId),
    onSuccess: () => invalidateQuote(queryClient, quoteId),
  });
}

export function useRejectQuote(quoteId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => rejectQuote(quoteId),
    onSuccess: () => invalidateQuote(queryClient, quoteId),
  });
}

export function useCancelQuote(quoteId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelQuote(quoteId),
    onSuccess: () => invalidateQuote(queryClient, quoteId),
  });
}

export function useConvertQuoteToOrder(quoteId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ConvertQuoteToOrder) => convertQuoteToOrder(quoteId, payload),
    onSuccess: () => {
      invalidateQuote(queryClient, quoteId);
      void queryClient.invalidateQueries({ queryKey: ["sales", "orders"] });
    },
  });
}
