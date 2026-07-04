/**
 * The return (RMA) workbench (STRUCTURE §4): post or cancel a draft return. Posting is
 * synchronous and reverses BOTH legs in one transaction — publishes ReturnReceived (inventory
 * RECEIPT move at book cost, reversing the original delivery's issue) and ReturnCredited
 * (finance posts a CustomerInvoice-shaped credit note: Dr revenue / Dr output tax / Cr AR
 * control — the same invoice machinery as billing, just sign-flipped; "credit note" is not a
 * separate model). POSTED is terminal; CANCELLED only from DRAFT.
 */

import { useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatMoney, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useBinLookup, useItemLookup, useWarehouseLookup } from "@/modules/inventory/hooks";
import { useCancelReturn, useCustomerOptions, usePostReturn, useReturn } from "@/modules/sales/hooks";

export function ReturnDetailPage() {
  const { returnId } = useParams({ strict: false });
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("sales.return.manage");
  const canPost = (me.data?.permissions ?? []).includes("sales.return.post");

  const returned = useReturn(returnId);
  const items = useItemLookup();
  const bins = useBinLookup();
  const customers = useCustomerOptions();
  const warehouses = useWarehouseLookup();
  const postReturn = usePostReturn(returnId ?? "");
  const cancelReturn = useCancelReturn(returnId ?? "");

  const [error, setError] = useState<string | null>(null);

  if (returned.isPending || !returned.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = returned.data;
  const isDraft = data.status === "DRAFT";

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };
  const binLabel = (id: string) => {
    const bin = bins.data?.items.find((b) => b.id === id);
    return bin ? bin.code : id;
  };
  const customerLabel = (id: string) => {
    const customer = customers.data?.items.find((c) => c.id === id);
    return customer ? `${customer.customer_code} — ${customer.name}` : id;
  };
  const warehouseLabel = (id: string) => {
    const warehouse = warehouses.data?.items.find((w) => w.id === id);
    return warehouse ? `${warehouse.code} — ${warehouse.name}` : id;
  };

  const post = async () => {
    setError(null);
    try {
      await postReturn.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to post the return."));
    }
  };

  const cancel = async () => {
    setError(null);
    try {
      await cancelReturn.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to cancel the return."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">{data.return_number}</h1>
        <div className="flex gap-2">
          {isDraft && canManage && (
            <button
              type="button"
              onClick={() => void cancel()}
              disabled={cancelReturn.isPending}
              className="rounded-control border border-line px-3 py-1.5 text-sm font-medium text-ink transition-colors duration-150 hover:border-danger hover:text-danger disabled:cursor-not-allowed disabled:opacity-45"
            >
              Cancel
            </button>
          )}
          {isDraft && canPost && (
            <button
              type="button"
              onClick={() => void post()}
              disabled={postReturn.isPending}
              className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
            >
              {postReturn.isPending ? "Posting…" : "Post"}
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
          <dt className="text-xs text-ink-muted">Customer</dt>
          <dd className="text-ink">{customerLabel(data.customer_id)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Warehouse</dt>
          <dd className="text-ink">{warehouseLabel(data.warehouse_id)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Reason</dt>
          <dd className="text-ink">{data.reason ?? "—"}</dd>
        </div>
      </dl>

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
            <th className="py-2 pr-2">Item</th>
            <th className="py-2 pr-2">Bin</th>
            <th className="py-2 pr-2 text-right">Quantity</th>
            <th className="py-2 pr-2 text-right">Unit price</th>
            <th className="py-2 pr-2 text-right">Line amount</th>
            <th className="py-2 pr-2">Lot / serial</th>
          </tr>
        </thead>
        <tbody>
          {data.lines.map((line) => (
            <tr key={line.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{itemLabel(line.item_id)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{binLabel(line.bin_id)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.quantity)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.unit_price, data.currency_code)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.line_amount, data.currency_code)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{line.lot_code ?? line.serial_code ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
