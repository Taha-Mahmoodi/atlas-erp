/**
 * Create a return (RMA) against a sales order (STRUCTURE §4). Orders with anything invoiced
 * but not yet fully returned are offered. One row per order line lets the operator enter a
 * quantity to return now (pre-filled to open-to-return = invoiced - returned) and a
 * destination bin for the returned stock; item_id/unit_price/tax are NOT entered here — the
 * backend snapshots them from the order line. Over-return (quantity > open-to-return) is
 * enforced server-side (422 sales.over_return); this form clamps the default but still
 * surfaces the 422 if raised anyway. Posting reverses both COGS (stock RECEIPT at book cost)
 * and revenue (a credit note) in one transaction.
 */

import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatQuantity } from "@/lib/format";
import { useBinOptions, useWarehouseOptions } from "@/modules/inventory/hooks";
import { useCreateReturn, useSalesOrder, useSalesOrders } from "@/modules/sales/hooks";
import type { ReturnLineCreate } from "@/modules/sales/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

const RETURNABLE_STATUSES = new Set(["PARTIALLY_DELIVERED", "DELIVERED", "INVOICED", "CLOSED"]);

export function ReturnFormPage() {
  const navigate = useNavigate();
  const orders = useSalesOrders();
  const returnableOrders = (orders.data?.pages.flatMap((page) => page.items) ?? []).filter((order) =>
    RETURNABLE_STATUSES.has(order.status),
  );
  const warehouses = useWarehouseOptions();

  const [salesOrderId, setSalesOrderId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [returnDate, setReturnDate] = useState(today());
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [lineInputs, setLineInputs] = useState<
    Record<string, Partial<{ quantity: string; binId: string; lotCode: string; serialCode: string }>>
  >({});
  const [error, setError] = useState<string | null>(null);

  const order = useSalesOrder(salesOrderId || undefined);
  const bins = useBinOptions(warehouseId || undefined);
  const createReturn = useCreateReturn();

  const openQuantity = (invoicedQuantity: string, returnedQuantity: string) =>
    (Number(invoicedQuantity) - Number(returnedQuantity)).toString();

  const setLineInput = (
    lineId: string,
    patch: Partial<{ quantity: string; binId: string; lotCode: string; serialCode: string }>,
  ) => {
    setLineInputs((prev) => ({ ...prev, [lineId]: { ...prev[lineId], ...patch } }));
  };

  const lines: ReturnLineCreate[] = (order.data?.lines ?? [])
    .map((line) => {
      const input = lineInputs[line.id];
      const quantity = input?.quantity ?? openQuantity(line.invoiced_quantity, line.returned_quantity);
      return {
        sales_order_line_id: line.id,
        bin_id: input?.binId ?? "",
        quantity,
        lot_code: input?.lotCode || null,
        serial_code: input?.serialCode || null,
      };
    })
    .filter((line) => line.bin_id && (Number(line.quantity) || 0) > 0);

  const canSubmit = Boolean(salesOrderId) && Boolean(warehouseId) && lines.length > 0;

  const submit = async () => {
    setError(null);
    try {
      const returned = await createReturn.mutateAsync({
        sales_order_id: salesOrderId,
        warehouse_id: warehouseId,
        return_date: returnDate || null,
        reason: reason || null,
        notes: notes || null,
        lines,
      });
      void navigate({ to: "/sales/returns/$returnId", params: { returnId: returned.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the return."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">New return</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 grid grid-cols-3 gap-4">
        <div>
          <label htmlFor="sales-order" className="mb-1 block text-xs font-medium text-ink-muted">
            Sales order
          </label>
          <select
            id="sales-order"
            value={salesOrderId}
            onChange={(event) => setSalesOrderId(event.target.value)}
            className={CONTROL}
          >
            <option value="">Select sales order</option>
            {returnableOrders.map((so) => (
              <option key={so.id} value={so.id}>
                {so.order_number}
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
          <label htmlFor="return-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Return date
          </label>
          <input
            id="return-date"
            type="date"
            value={returnDate}
            onChange={(event) => setReturnDate(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div>
          <label htmlFor="reason" className="mb-1 block text-xs font-medium text-ink-muted">
            Reason
          </label>
          <input
            id="reason"
            type="text"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div className="col-span-2">
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

      {salesOrderId && warehouseId && (
        <div className="mt-6">
          {order.isPending ? (
            <p className="text-sm text-ink-muted">Loading sales order lines…</p>
          ) : (
            <table className="w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
                  <th className="py-2 pr-2">Line</th>
                  <th className="py-2 pr-2 text-right">Invoiced</th>
                  <th className="py-2 pr-2 text-right">Returned</th>
                  <th className="py-2 pr-2 text-right">Open</th>
                  <th className="w-28 py-2 pr-2 text-right">Return now</th>
                  <th className="py-2 pr-2">Bin</th>
                  <th className="py-2 pr-2">Lot code</th>
                </tr>
              </thead>
              <tbody>
                {(order.data?.lines ?? []).map((line) => {
                  const open = openQuantity(line.invoiced_quantity, line.returned_quantity);
                  const input = lineInputs[line.id];
                  return (
                    <tr key={line.id} className="border-b border-line last:border-b-0">
                      <td className="py-1.5 pr-2 text-ink">Line {line.line_number}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.invoiced_quantity)}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.returned_quantity)}</td>
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
        disabled={!canSubmit || createReturn.isPending}
        className="mt-6 btn-ink"
      >
        {createReturn.isPending ? "Creating…" : "Create draft"}
      </button>
    </div>
  );
}
