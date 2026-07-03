/**
 * Create a goods receipt against a purchase order (STRUCTURE §4). Only POs in a receivable
 * status (SENT/APPROVED/PARTIALLY_RECEIVED) are offered. Once a PO and warehouse are chosen,
 * one row per PO line lets the operator enter a received quantity (defaulted to the line's
 * open quantity = quantity - received_quantity) and a bin; item_id/unit_cost are NOT entered
 * here — the backend snapshots them from the PO line. Over-receipt (quantity > open quantity)
 * is enforced server-side (422 procurement.over_receipt); this form clamps the default to the
 * open quantity but still surfaces the 422 message if the operator raises it anyway.
 */

import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatQuantity } from "@/lib/format";
import { useBinOptions, useWarehouseOptions } from "@/modules/inventory/hooks";
import { useCreateGoodsReceipt, usePurchaseOrder, usePurchaseOrders } from "@/modules/procurement/hooks";
import type { GoodsReceiptLineCreate } from "@/modules/procurement/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

const RECEIVABLE_STATUSES = new Set(["SENT", "APPROVED", "PARTIALLY_RECEIVED"]);

export function GoodsReceiptFormPage() {
  const navigate = useNavigate();
  const orders = usePurchaseOrders();
  const receivableOrders = (orders.data?.pages.flatMap((page) => page.items) ?? []).filter((order) =>
    RECEIVABLE_STATUSES.has(order.status),
  );
  const warehouses = useWarehouseOptions();

  const [purchaseOrderId, setPurchaseOrderId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [receiptDate, setReceiptDate] = useState(today());
  const [notes, setNotes] = useState("");
  const [lineInputs, setLineInputs] = useState<Record<string, { quantity: string; binId: string; lotCode: string }>>({});
  const [error, setError] = useState<string | null>(null);

  const order = usePurchaseOrder(purchaseOrderId || undefined);
  const bins = useBinOptions(warehouseId || undefined);
  const createGoodsReceipt = useCreateGoodsReceipt();

  const openQuantity = (quantity: string, receivedQuantity: string) =>
    (Number(quantity) - Number(receivedQuantity)).toString();

  const setLineInput = (lineId: string, patch: Partial<{ quantity: string; binId: string; lotCode: string }>) => {
    setLineInputs((prev) => ({ ...prev, [lineId]: { quantity: "", binId: "", lotCode: "", ...prev[lineId], ...patch } }));
  };

  const lines: GoodsReceiptLineCreate[] = (order.data?.lines ?? [])
    .map((line) => {
      const input = lineInputs[line.id];
      const quantity = input?.quantity ?? openQuantity(line.quantity, line.received_quantity);
      return {
        purchase_order_line_id: line.id,
        bin_id: input?.binId ?? "",
        received_quantity: quantity,
        lot_code: input?.lotCode || null,
      };
    })
    .filter((line) => line.bin_id && (Number(line.received_quantity) || 0) > 0);

  const canSubmit = Boolean(purchaseOrderId) && Boolean(warehouseId) && lines.length > 0;

  const submit = async () => {
    setError(null);
    try {
      const receipt = await createGoodsReceipt.mutateAsync({
        purchase_order_id: purchaseOrderId,
        warehouse_id: warehouseId,
        receipt_date: receiptDate || null,
        notes: notes || null,
        lines,
      });
      void navigate({ to: "/procurement/goods-receipts/$goodsReceiptId", params: { goodsReceiptId: receipt.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the goods receipt."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-xl font-semibold text-ink">New goods receipt</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 grid grid-cols-3 gap-4">
        <div>
          <label htmlFor="purchase-order" className="mb-1 block text-xs font-medium text-ink-muted">
            Purchase order
          </label>
          <select
            id="purchase-order"
            value={purchaseOrderId}
            onChange={(event) => setPurchaseOrderId(event.target.value)}
            className={CONTROL}
          >
            <option value="">Select purchase order</option>
            {receivableOrders.map((po) => (
              <option key={po.id} value={po.id}>
                {po.po_number}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="warehouse" className="mb-1 block text-xs font-medium text-ink-muted">
            Warehouse
          </label>
          <select
            id="warehouse"
            value={warehouseId}
            onChange={(event) => setWarehouseId(event.target.value)}
            className={CONTROL}
          >
            <option value="">Select warehouse</option>
            {(warehouses.data?.items ?? []).map((warehouse) => (
              <option key={warehouse.id} value={warehouse.id}>
                {warehouse.code} — {warehouse.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="receipt-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Receipt date
          </label>
          <input
            id="receipt-date"
            type="date"
            value={receiptDate}
            onChange={(event) => setReceiptDate(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div className="col-span-3">
          <label htmlFor="notes" className="mb-1 block text-xs font-medium text-ink-muted">
            Notes
          </label>
          <input
            id="notes"
            type="text"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            className={CONTROL}
          />
        </div>
      </div>

      {purchaseOrderId && warehouseId && (
        <div className="mt-6">
          {order.isPending ? (
            <p className="text-sm text-ink-muted">Loading purchase order lines…</p>
          ) : (
            <table className="w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
                  <th className="py-2 pr-2">Line</th>
                  <th className="py-2 pr-2 text-right">Ordered</th>
                  <th className="py-2 pr-2 text-right">Received</th>
                  <th className="py-2 pr-2 text-right">Open</th>
                  <th className="w-28 py-2 pr-2 text-right">Receive now</th>
                  <th className="py-2 pr-2">Bin</th>
                  <th className="py-2 pr-2">Lot code</th>
                </tr>
              </thead>
              <tbody>
                {(order.data?.lines ?? []).map((line) => {
                  const open = openQuantity(line.quantity, line.received_quantity);
                  const input = lineInputs[line.id];
                  return (
                    <tr key={line.id} className="border-b border-line last:border-b-0">
                      <td className="py-1.5 pr-2 text-ink">Line {line.line_number}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.quantity)}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.received_quantity)}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(open)}</td>
                      <td className="py-1.5 pr-2">
                        <input
                          type="number"
                          step="0.000001"
                          value={input?.quantity ?? open}
                          onChange={(event) => setLineInput(line.id, { quantity: event.target.value })}
                          className="w-full rounded-control border border-line bg-surface px-2 py-1 text-right text-sm tabular-nums"
                        />
                      </td>
                      <td className="py-1.5 pr-2">
                        <select
                          value={input?.binId ?? ""}
                          onChange={(event) => setLineInput(line.id, { binId: event.target.value })}
                          className="w-full rounded-control border border-line bg-surface px-2 py-1 text-sm"
                        >
                          <option value="">Select bin</option>
                          {(bins.data?.items ?? []).map((bin) => (
                            <option key={bin.id} value={bin.id}>
                              {bin.code}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="py-1.5 pr-2">
                        <input
                          type="text"
                          value={input?.lotCode ?? ""}
                          onChange={(event) => setLineInput(line.id, { lotCode: event.target.value })}
                          className="w-full rounded-control border border-line bg-surface px-2 py-1 text-sm"
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit || createGoodsReceipt.isPending}
        className="mt-6 rounded-control bg-primary px-4 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
      >
        {createGoodsReceipt.isPending ? "Creating…" : "Create draft"}
      </button>
    </div>
  );
}
