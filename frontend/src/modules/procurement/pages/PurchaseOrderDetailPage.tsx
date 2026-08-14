/**
 * The purchase order workbench (STRUCTURE §4): send for approval/dispatch, decide
 * (approve/reject) when a PURCHASE_ORDER approval rule applies, cancel. received_quantity
 * per line is server-maintained by goods-receipt posting (a later slice) — read-only here.
 */

import { useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatMoney, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useItemLookup, useUomOptions } from "@/modules/inventory/hooks";
import {
  useCancelPurchaseOrder,
  useDecidePurchaseOrder,
  usePurchaseOrder,
  useSendPurchaseOrder,
  useVendorLookup,
} from "@/modules/procurement/hooks";

export function PurchaseOrderDetailPage() {
  const { purchaseOrderId } = useParams({ strict: false });
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("procurement.po.manage");
  const canApprove = (me.data?.permissions ?? []).includes("procurement.po.approve");

  const order = usePurchaseOrder(purchaseOrderId);
  const items = useItemLookup();
  const uoms = useUomOptions();
  const vendors = useVendorLookup();
  const sendOrder = useSendPurchaseOrder(purchaseOrderId ?? "");
  const decideOrder = useDecidePurchaseOrder(purchaseOrderId ?? "");
  const cancelOrder = useCancelPurchaseOrder(purchaseOrderId ?? "");

  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (order.isPending || !order.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = order.data;
  const canSend = data.status === "DRAFT" || data.status === "APPROVED";
  const canDecide = data.status === "PENDING_APPROVAL";
  const canCancel = data.status !== "CLOSED" && data.status !== "CANCELLED" && data.status !== "REJECTED";

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };
  const uomLabel = (id: string) => {
    const uom = uoms.data?.items.find((u) => u.id === id);
    return uom ? uom.code : id;
  };
  const vendorLabel = (id: string) => {
    const vendor = vendors.data?.items.find((v) => v.id === id);
    return vendor ? `${vendor.vendor_code} — ${vendor.name}` : id;
  };

  const send = async () => {
    setError(null);
    try {
      await sendOrder.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to send the purchase order."));
    }
  };

  const decide = async (decision: "APPROVED" | "REJECTED") => {
    setError(null);
    try {
      await decideOrder.mutateAsync({ decision, comment: comment || null });
      setComment("");
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to record the decision."));
    }
  };

  const cancel = async () => {
    setError(null);
    try {
      await cancelOrder.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to cancel the purchase order."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.po_number}</h1>
        <div className="flex gap-2">
          {canCancel && canManage && (
            <button
              type="button"
              onClick={() => void cancel()}
              disabled={cancelOrder.isPending}
              className="btn-chip hover:border-danger hover:text-danger"
            >
              Cancel
            </button>
          )}
          {canSend && canManage && (
            <button
              type="button"
              onClick={() => void send()}
              disabled={sendOrder.isPending}
              className="btn-ink"
            >
              {sendOrder.isPending ? "Sending…" : "Send"}
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
          <dd className="text-ink">{data.status.replace("_", " ")}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Vendor</dt>
          <dd className="text-ink">{vendorLabel(data.vendor_id)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Expected date</dt>
          <dd className="text-ink">{data.expected_date ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Total</dt>
          <dd className="text-ink">{formatMoney(data.total_amount, data.currency_code)}</dd>
        </div>
      </dl>

      {canDecide && canApprove && (
        <div className="mt-6 rounded-card border border-line bg-surface p-4 shadow-card">
          <h2 className="text-sm font-semibold text-ink">Decision</h2>
          <label htmlFor="comment" className="mb-1 mt-3 block text-xs font-medium text-ink-muted">
            Comment (optional)
          </label>
          <textarea
            id="comment"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          />
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => void decide("APPROVED")}
              disabled={decideOrder.isPending}
              className="rounded-control bg-success px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
            >
              Approve
            </button>
            <button
              type="button"
              onClick={() => void decide("REJECTED")}
              disabled={decideOrder.isPending}
              className="rounded-control bg-danger px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
            >
              Reject
            </button>
          </div>
        </div>
      )}

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-2 pr-2">Item</th>
            <th className="py-2 pr-2">Description</th>
            <th className="py-2 pr-2 text-right">Quantity</th>
            <th className="py-2 pr-2">UoM</th>
            <th className="py-2 pr-2 text-right">Unit cost</th>
            <th className="py-2 pr-2 text-right">Received</th>
          </tr>
        </thead>
        <tbody>
          {data.lines.map((line) => (
            <tr key={line.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{itemLabel(line.item_id)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{line.description ?? "—"}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.quantity)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{uomLabel(line.uom_id)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.unit_cost, data.currency_code)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.received_quantity)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
