import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelInvoiceMatch,
  createInvoiceMatch,
  getGoodsReceipt,
  getInvoiceMatch,
  getMatchTolerance,
  type InvoiceMatchFilters,
  listGoodsReceipts,
  listInvoiceMatches,
  overrideInvoiceMatch,
  postInvoiceMatch,
  setMatchTolerance,
} from "@/modules/procurement/api";
import type { InvoiceMatchCreate, MatchToleranceUpsert } from "@/modules/procurement/types";

/** Every POSTED goods-receipt line for a PO, flattened — used to let a match line optionally
 * reference the specific receipt it's invoicing against (changes partial-invoice variance
 * semantics, see types.ts). A PO typically has few receipts, so fetching each one's detail
 * for its lines (list only returns headers) is a small, bounded fan-out, not a real N+1. */
export function useGoodsReceiptLinesForPurchaseOrder(purchaseOrderId: string | undefined) {
  return useQuery({
    queryKey: ["procurement", "goods-receipt-lines-for-po", purchaseOrderId],
    queryFn: async () => {
      const page = await listGoodsReceipts({ purchase_order_id: purchaseOrderId as string, status: "POSTED", limit: 50 });
      const details = await Promise.all(page.items.map((receipt) => getGoodsReceipt(receipt.id)));
      return details.flatMap((receipt) =>
        receipt.lines.map((line) => ({ ...line, gr_number: receipt.gr_number })),
      );
    },
    enabled: purchaseOrderId !== undefined,
  });
}

export function useInvoiceMatches(filters: Omit<InvoiceMatchFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["procurement", "invoice-matches", filters],
    queryFn: ({ pageParam }) =>
      listInvoiceMatches({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useInvoiceMatch(invoiceMatchId: string | undefined) {
  return useQuery({
    queryKey: ["procurement", "invoice-match", invoiceMatchId],
    queryFn: () => getInvoiceMatch(invoiceMatchId as string),
    enabled: invoiceMatchId !== undefined,
  });
}

function invalidateInvoiceMatch(queryClient: ReturnType<typeof useQueryClient>, invoiceMatchId: string) {
  void queryClient.invalidateQueries({ queryKey: ["procurement", "invoice-matches"] });
  void queryClient.invalidateQueries({ queryKey: ["procurement", "invoice-match", invoiceMatchId] });
}

export function useCreateInvoiceMatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: InvoiceMatchCreate) => createInvoiceMatch(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["procurement", "invoice-matches"] });
    },
  });
}

export function usePostInvoiceMatch(invoiceMatchId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => postInvoiceMatch(invoiceMatchId),
    onSuccess: () => {
      invalidateInvoiceMatch(queryClient, invoiceMatchId);
      void queryClient.invalidateQueries({ queryKey: ["finance", "vendor-bills"] });
    },
  });
}

export function useOverrideInvoiceMatch(invoiceMatchId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => overrideInvoiceMatch(invoiceMatchId),
    onSuccess: () => invalidateInvoiceMatch(queryClient, invoiceMatchId),
  });
}

export function useCancelInvoiceMatch(invoiceMatchId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelInvoiceMatch(invoiceMatchId),
    onSuccess: () => invalidateInvoiceMatch(queryClient, invoiceMatchId),
  });
}

export function useMatchTolerance() {
  return useQuery({
    queryKey: ["procurement", "match-tolerance"],
    queryFn: () => getMatchTolerance(),
  });
}

export function useSetMatchTolerance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: MatchToleranceUpsert) => setMatchTolerance(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["procurement", "match-tolerance"] });
    },
  });
}
