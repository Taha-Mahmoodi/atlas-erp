/**
 * Create a billing against a sales order (STRUCTURE §4). Only orders with something delivered
 * but not yet fully invoiced (PARTIALLY_DELIVERED/DELIVERED) are offered. One row per order
 * line lets the operator enter a quantity to bill now (pre-filled to open-to-bill = delivered -
 * invoiced); item_id/unit_price/discount/tax are NOT entered here — the backend snapshots them
 * from the order line. Over-billing (quantity > open-to-bill) is enforced server-side (422
 * sales.over_billing); this form clamps the default but still surfaces the 422 if raised
 * anyway. `delivery_line_id` (an optional docflow pointer to a specific delivery) is left unset
 * — it doesn't affect the invoiced amount, only which delivery a line's history points at, and
 * a billing can span multiple deliveries regardless.
 */

import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatQuantity } from "@/lib/format";
import { useSalesOrder, useSalesOrders, useCreateBilling } from "@/modules/sales/hooks";
import type { BillingLineCreate } from "@/modules/sales/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

const BILLABLE_STATUSES = new Set(["PARTIALLY_DELIVERED", "DELIVERED"]);

export function BillingFormPage() {
  const navigate = useNavigate();
  const orders = useSalesOrders();
  const billableOrders = (orders.data?.pages.flatMap((page) => page.items) ?? []).filter((order) =>
    BILLABLE_STATUSES.has(order.status),
  );

  const [salesOrderId, setSalesOrderId] = useState("");
  const [billingDate, setBillingDate] = useState(today());
  const [notes, setNotes] = useState("");
  const [lineInputs, setLineInputs] = useState<Record<string, Partial<{ quantity: string }>>>({});
  const [error, setError] = useState<string | null>(null);

  const order = useSalesOrder(salesOrderId || undefined);
  const createBilling = useCreateBilling();

  const openQuantity = (deliveredQuantity: string, invoicedQuantity: string) =>
    (Number(deliveredQuantity) - Number(invoicedQuantity)).toString();

  const setLineInput = (lineId: string, patch: Partial<{ quantity: string }>) => {
    setLineInputs((prev) => ({ ...prev, [lineId]: { ...prev[lineId], ...patch } }));
  };

  const lines: BillingLineCreate[] = (order.data?.lines ?? [])
    .map((line) => {
      const input = lineInputs[line.id];
      const quantity = input?.quantity ?? openQuantity(line.delivered_quantity, line.invoiced_quantity);
      return { sales_order_line_id: line.id, quantity };
    })
    .filter((line) => (Number(line.quantity) || 0) > 0);

  const canSubmit = Boolean(salesOrderId) && lines.length > 0;

  const submit = async () => {
    setError(null);
    try {
      const billing = await createBilling.mutateAsync({
        sales_order_id: salesOrderId,
        billing_date: billingDate || null,
        notes: notes || null,
        lines,
      });
      void navigate({ to: "/sales/billings/$billingId", params: { billingId: billing.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the billing."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">New billing</h1>
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
            {billableOrders.map((so) => (
              <option key={so.id} value={so.id}>
                {so.order_number}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="billing-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Billing date
          </label>
          <input
            id="billing-date"
            type="date"
            value={billingDate}
            onChange={(event) => setBillingDate(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div>
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

      {salesOrderId && (
        <div className="mt-6">
          {order.isPending ? (
            <p className="text-sm text-ink-muted">Loading sales order lines…</p>
          ) : (
            <table className="w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
                  <th className="py-2 pr-2">Line</th>
                  <th className="py-2 pr-2 text-right">Delivered</th>
                  <th className="py-2 pr-2 text-right">Invoiced</th>
                  <th className="py-2 pr-2 text-right">Open</th>
                  <th className="w-28 py-2 pr-2 text-right">Bill now</th>
                </tr>
              </thead>
              <tbody>
                {(order.data?.lines ?? []).map((line) => {
                  const open = openQuantity(line.delivered_quantity, line.invoiced_quantity);
                  const input = lineInputs[line.id];
                  return (
                    <tr key={line.id} className="border-b border-line last:border-b-0">
                      <td className="py-1.5 pr-2 text-ink">Line {line.line_number}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.delivered_quantity)}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.invoiced_quantity)}</td>
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
        disabled={!canSubmit || createBilling.isPending}
        className="mt-6 btn-ink"
      >
        {createBilling.isPending ? "Creating…" : "Create draft"}
      </button>
    </div>
  );
}
