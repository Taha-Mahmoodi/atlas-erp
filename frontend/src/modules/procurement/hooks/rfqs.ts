import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  closeRfq,
  convertRfqToPurchaseOrder,
  createRfq,
  getRfq,
  listRfqs,
  recordRfqQuote,
  type RfqFilters,
  sendRfq,
} from "@/modules/procurement/api";
import type { PurchaseOrderFromRfq, RecordQuotePayload, RfqCreate } from "@/modules/procurement/types";

export function useRfqs(filters: Omit<RfqFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["procurement", "rfqs", filters],
    queryFn: ({ pageParam }) => listRfqs({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useRfq(rfqId: string | undefined) {
  return useQuery({
    queryKey: ["procurement", "rfq", rfqId],
    queryFn: () => getRfq(rfqId as string),
    enabled: rfqId !== undefined,
  });
}

function invalidateRfq(queryClient: ReturnType<typeof useQueryClient>, rfqId: string) {
  void queryClient.invalidateQueries({ queryKey: ["procurement", "rfqs"] });
  void queryClient.invalidateQueries({ queryKey: ["procurement", "rfq", rfqId] });
}

export function useCreateRfq() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RfqCreate) => createRfq(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["procurement", "rfqs"] });
    },
  });
}

export function useSendRfq(rfqId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => sendRfq(rfqId),
    onSuccess: () => invalidateRfq(queryClient, rfqId),
  });
}

export function useRecordRfqQuote(rfqId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RecordQuotePayload) => recordRfqQuote(rfqId, payload),
    onSuccess: () => invalidateRfq(queryClient, rfqId),
  });
}

export function useCloseRfq(rfqId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => closeRfq(rfqId),
    onSuccess: () => invalidateRfq(queryClient, rfqId),
  });
}

export function useConvertRfqToPurchaseOrder(rfqId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PurchaseOrderFromRfq) => convertRfqToPurchaseOrder(rfqId, payload),
    onSuccess: () => {
      invalidateRfq(queryClient, rfqId);
      void queryClient.invalidateQueries({ queryKey: ["procurement", "purchase-orders"] });
    },
  });
}
