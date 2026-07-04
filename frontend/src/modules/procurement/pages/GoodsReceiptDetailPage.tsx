/**
 * The goods receipt workbench (STRUCTURE §4): post or cancel a draft receipt. Posting is
 * synchronous, not a background job — it publishes GoodsReceiptPosted in the same transaction,
 * which inventory and finance handle to create the stock RECEIPT moves and post the GR/IR
 * journal. POSTED is terminal (no un-post); CANCELLED only from DRAFT.
 */

import { useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatMoney, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useBinLookup, useItemLookup, useWarehouseLookup } from "@/modules/inventory/hooks";
import { useFunctionalCurrency } from "@/modules/finance/hooks";
import {
  useCancelGoodsReceipt,
  useGoodsReceipt,
  usePostGoodsReceipt,
  useVendorLookup,
} from "@/modules/procurement/hooks";

export function GoodsReceiptDetailPage() {
  const { goodsReceiptId } = useParams({ strict: false });
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("procurement.goods_receipt.manage");
  const canPost = (me.data?.permissions ?? []).includes("procurement.goods_receipt.post");

  const receipt = useGoodsReceipt(goodsReceiptId);
  const items = useItemLookup();
  const bins = useBinLookup();
  const vendors = useVendorLookup();
  const warehouses = useWarehouseLookup();
  const currency = useFunctionalCurrency();
  const postReceipt = usePostGoodsReceipt(goodsReceiptId ?? "");
  const cancelReceipt = useCancelGoodsReceipt(goodsReceiptId ?? "");

  const [error, setError] = useState<string | null>(null);

  if (receipt.isPending || !receipt.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = receipt.data;
  const isDraft = data.status === "DRAFT";
  const currencyCode = currency.data ?? "—";

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };
  const binLabel = (id: string) => {
    const bin = bins.data?.items.find((b) => b.id === id);
    return bin ? bin.code : id;
  };
  const vendorLabel = (id: string) => {
    const vendor = vendors.data?.items.find((v) => v.id === id);
    return vendor ? `${vendor.vendor_code} — ${vendor.name}` : id;
  };
  const warehouseLabel = (id: string) => {
    const warehouse = warehouses.data?.items.find((w) => w.id === id);
    return warehouse ? `${warehouse.code} — ${warehouse.name}` : id;
  };

  const post = async () => {
    setError(null);
    try {
      await postReceipt.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to post the goods receipt."));
    }
  };

  const cancel = async () => {
    setError(null);
    try {
      await cancelReceipt.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to cancel the goods receipt."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">{data.gr_number}</h1>
        <div className="flex gap-2">
          {isDraft && canManage && (
            <button
              type="button"
              onClick={() => void cancel()}
              disabled={cancelReceipt.isPending}
              className="rounded-control border border-line px-3 py-1.5 text-sm font-medium text-ink transition-colors duration-150 hover:border-danger hover:text-danger disabled:cursor-not-allowed disabled:opacity-45"
            >
              Cancel
            </button>
          )}
          {isDraft && canPost && (
            <button
              type="button"
              onClick={() => void post()}
              disabled={postReceipt.isPending}
              className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
            >
              {postReceipt.isPending ? "Posting…" : "Post"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <dl className="mt-6 grid grid-cols-4 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Status</dt>
          <dd className="text-ink">{data.status}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Vendor</dt>
          <dd className="text-ink">{vendorLabel(data.vendor_id)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Warehouse</dt>
          <dd className="text-ink">{warehouseLabel(data.warehouse_id)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Receipt date</dt>
          <dd className="text-ink">{data.receipt_date}</dd>
        </div>
      </dl>

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
            <th className="py-2 pr-2">Item</th>
            <th className="py-2 pr-2">Bin</th>
            <th className="py-2 pr-2 text-right">Received qty</th>
            <th className="py-2 pr-2 text-right">Unit cost</th>
            <th className="py-2 pr-2">Lot / serial</th>
          </tr>
        </thead>
        <tbody>
          {data.lines.map((line) => (
            <tr key={line.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{itemLabel(line.item_id)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{binLabel(line.bin_id)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.received_quantity)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.unit_cost, currencyCode)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{line.lot_code ?? line.serial_code ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
