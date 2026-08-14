/**
 * Create a delivery against a sales order (STRUCTURE §4). Only orders in a deliverable status
 * (CONFIRMED/PARTIALLY_DELIVERED) are offered. Once an order and warehouse are chosen, one row
 * per order line lets the operator enter a quantity to deliver now (defaulted to the line's
 * open-to-deliver = ordered - delivered) and a source bin; item_id is NOT entered here — the
 * backend snapshots it from the order line. Over-delivery (quantity > open-to-deliver) is
 * enforced server-side (422 sales.over_delivery); this form clamps the default to the open
 * quantity but still surfaces the 422 message if the operator raises it anyway. No distinct
 * "backorder" object exists — an order simply stays PARTIALLY_DELIVERED until every line is
 * fully delivered, and further deliveries can be created against it in the meantime.
 */

import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatQuantity } from "@/lib/format";
import { useBinOptions, useWarehouseOptions } from "@/modules/inventory/hooks";
import { useCreateDelivery, useSalesOrder, useSalesOrders } from "@/modules/sales/hooks";
import type { DeliveryLineCreate } from "@/modules/sales/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

const DELIVERABLE_STATUSES = new Set(["CONFIRMED", "PARTIALLY_DELIVERED"]);

export function DeliveryFormPage() {
  const navigate = useNavigate();
  const orders = useSalesOrders();
  const deliverableOrders = (orders.data?.pages.flatMap((page) => page.items) ?? []).filter((order) =>
    DELIVERABLE_STATUSES.has(order.status),
  );
  const warehouses = useWarehouseOptions();

  const [salesOrderId, setSalesOrderId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const [deliveryDate, setDeliveryDate] = useState(today());
  const [shippingAddress, setShippingAddress] = useState("");
  const [notes, setNotes] = useState("");
  const [lineInputs, setLineInputs] = useState<
    Record<string, Partial<{ quantity: string; binId: string; lotCode: string; serialCode: string }>>
  >({});
  const [error, setError] = useState<string | null>(null);

  const order = useSalesOrder(salesOrderId || undefined);
  const bins = useBinOptions(warehouseId || undefined);
  const createDelivery = useCreateDelivery();

  const openQuantity = (orderedQuantity: string, deliveredQuantity: string) =>
    (Number(orderedQuantity) - Number(deliveredQuantity)).toString();

  const setLineInput = (
    lineId: string,
    patch: Partial<{ quantity: string; binId: string; lotCode: string; serialCode: string }>,
  ) => {
    setLineInputs((prev) => ({ ...prev, [lineId]: { ...prev[lineId], ...patch } }));
  };

  const lines: DeliveryLineCreate[] = (order.data?.lines ?? [])
    .map((line) => {
      const input = lineInputs[line.id];
      const quantity = input?.quantity ?? openQuantity(line.ordered_quantity, line.delivered_quantity);
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
      const delivery = await createDelivery.mutateAsync({
        sales_order_id: salesOrderId,
        warehouse_id: warehouseId,
        delivery_date: deliveryDate || null,
        shipping_address: shippingAddress || null,
        notes: notes || null,
        lines,
      });
      void navigate({ to: "/sales/deliveries/$deliveryId", params: { deliveryId: delivery.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the delivery."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">New delivery</h1>
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
            {deliverableOrders.map((so) => (
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
          <label htmlFor="delivery-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Delivery date
          </label>
          <input
            id="delivery-date"
            type="date"
            value={deliveryDate}
            onChange={(event) => setDeliveryDate(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div className="col-span-2">
          <label htmlFor="shipping-address" className="mb-1 block text-xs font-medium text-ink-muted">
            Shipping address
          </label>
          <input
            id="shipping-address"
            type="text"
            value={shippingAddress}
            onChange={(event) => setShippingAddress(event.target.value)}
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

      {salesOrderId && warehouseId && (
        <div className="mt-6">
          {order.isPending ? (
            <p className="text-sm text-ink-muted">Loading sales order lines…</p>
          ) : (
            <table className="w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b border-line text-left mono-caps text-ink-muted">
                  <th className="py-2 pr-2">Line</th>
                  <th className="py-2 pr-2 text-right">Ordered</th>
                  <th className="py-2 pr-2 text-right">Delivered</th>
                  <th className="py-2 pr-2 text-right">Open</th>
                  <th className="w-28 py-2 pr-2 text-right">Deliver now</th>
                  <th className="py-2 pr-2">Bin</th>
                  <th className="py-2 pr-2">Lot code</th>
                </tr>
              </thead>
              <tbody>
                {(order.data?.lines ?? []).map((line) => {
                  const open = openQuantity(line.ordered_quantity, line.delivered_quantity);
                  const input = lineInputs[line.id];
                  return (
                    <tr key={line.id} className="border-b border-line last:border-b-0">
                      <td className="py-1.5 pr-2 text-ink">Line {line.line_number}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.ordered_quantity)}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.delivered_quantity)}</td>
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
        disabled={!canSubmit || createDelivery.isPending}
        className="mt-6 btn-ink"
      >
        {createDelivery.isPending ? "Creating…" : "Create draft"}
      </button>
    </div>
  );
}
