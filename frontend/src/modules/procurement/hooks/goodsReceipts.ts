import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  cancelGoodsReceipt,
  createGoodsReceipt,
  getGoodsReceipt,
  type GoodsReceiptFilters,
  listGoodsReceipts,
  postGoodsReceipt,
} from "@/modules/procurement/api";
import type { GoodsReceiptCreate } from "@/modules/procurement/types";

export function useGoodsReceipts(filters: Omit<GoodsReceiptFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["procurement", "goods-receipts", filters],
    queryFn: ({ pageParam }) =>
      listGoodsReceipts({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useGoodsReceipt(goodsReceiptId: string | undefined) {
  return useQuery({
    queryKey: ["procurement", "goods-receipt", goodsReceiptId],
    queryFn: () => getGoodsReceipt(goodsReceiptId as string),
    enabled: goodsReceiptId !== undefined,
  });
}

function invalidateGoodsReceipt(queryClient: ReturnType<typeof useQueryClient>, goodsReceiptId: string) {
  void queryClient.invalidateQueries({ queryKey: ["procurement", "goods-receipts"] });
  void queryClient.invalidateQueries({ queryKey: ["procurement", "goods-receipt", goodsReceiptId] });
}

export function useCreateGoodsReceipt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: GoodsReceiptCreate) => createGoodsReceipt(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["procurement", "goods-receipts"] });
    },
  });
}

export function usePostGoodsReceipt(goodsReceiptId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => postGoodsReceipt(goodsReceiptId),
    onSuccess: () => {
      invalidateGoodsReceipt(queryClient, goodsReceiptId);
      void queryClient.invalidateQueries({ queryKey: ["procurement", "purchase-order"] });
      void queryClient.invalidateQueries({ queryKey: ["inventory"] });
    },
  });
}

export function useCancelGoodsReceipt(goodsReceiptId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => cancelGoodsReceipt(goodsReceiptId),
    onSuccess: () => invalidateGoodsReceipt(queryClient, goodsReceiptId),
  });
}
