/**
 * Create or edit a sales order (STRUCTURE §4). Edit mode via `/sales/orders/$orderId/edit`;
 * create via `/sales/orders/new`. Only a DRAFT order is editable (a CONFIRMED order is a firm
 * commitment) — PATCH replaces the whole line set wholesale, so this page always submits the
 * full current line array, never a diff (mirrors procurement's RequisitionFormPage).
 */

import { useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useTaxCodes } from "@/modules/finance/hooks";
import { useItemOptions, useUomOptions } from "@/modules/inventory/hooks";
import { SalesOrderLinesEditor } from "@/modules/sales/components/SalesOrderLinesEditor";
import { useCreateSalesOrder, useCustomerOptions, useSalesOrder, useUpdateSalesOrder } from "@/modules/sales/hooks";
import type { SalesOrderLineCreate } from "@/modules/sales/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function SalesOrderFormPage() {
  const { orderId } = useParams({ strict: false });
  const isEdit = orderId !== undefined;
  const navigate = useNavigate();

  const order = useSalesOrder(orderId);
  const customers = useCustomerOptions();
  const items = useItemOptions();
  const uoms = useUomOptions();
  const taxCodes = useTaxCodes();
  const createOrder = useCreateSalesOrder();
  const updateOrder = useUpdateSalesOrder(orderId ?? "");

  const [customerId, setCustomerId] = useState("");
  const [currencyCode, setCurrencyCode] = useState("USD");
  const [orderDate, setOrderDate] = useState(today());
  const [requestedDate, setRequestedDate] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<SalesOrderLineCreate[]>([{ item_id: "", quantity: "", uom_id: "" }]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (order.data) {
      setCustomerId(order.data.customer_id);
      setCurrencyCode(order.data.currency_code);
      setOrderDate(order.data.order_date);
      setRequestedDate(order.data.requested_date ?? "");
      setNotes(order.data.notes ?? "");
      setLines(
        order.data.lines.map((line) => ({
          item_id: line.item_id,
          description: line.description,
          quantity: line.ordered_quantity,
          uom_id: line.uom_id,
          unit_price: line.unit_price,
          discount_type: line.discount_type,
          discount_value: line.discount_value,
          tax_code_id: line.tax_code_id,
        })),
      );
    }
  }, [order.data]);

  const validLines = lines.filter((line) => line.item_id && line.uom_id && (Number(line.quantity) || 0) > 0);
  const canSubmit = Boolean(customerId) && validLines.length > 0;

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        currency_code: currencyCode,
        order_date: orderDate || null,
        requested_date: requestedDate || null,
        notes: notes || null,
        lines: validLines,
      };
      if (isEdit) {
        await updateOrder.mutateAsync(shared);
        void navigate({ to: "/sales/orders/$orderId", params: { orderId } });
      } else {
        const created = await createOrder.mutateAsync({ ...shared, customer_id: customerId });
        void navigate({ to: "/sales/orders/$orderId", params: { orderId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the sales order."));
    }
  };

  const busy = createOrder.isPending || updateOrder.isPending;

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{isEdit ? "Edit sales order" : "New sales order"}</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 grid grid-cols-4 gap-4">
        <div>
          <label htmlFor="customer" className="mb-1 block text-xs font-medium text-ink-muted">
            Customer
          </label>
          <select
            id="customer"
            value={customerId}
            onChange={(event) => setCustomerId(event.target.value)}
            disabled={isEdit}
            className={CONTROL}
          >
            <option value="">Select customer</option>
            {(customers.data?.items ?? []).map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.customer_code} — {customer.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="currency" className="mb-1 block text-xs font-medium text-ink-muted">
            Currency
          </label>
          <input
            id="currency"
            type="text"
            value={currencyCode}
            onChange={(event) => setCurrencyCode(event.target.value.toUpperCase())}
            maxLength={3}
            className={CONTROL}
          />
        </div>
        <div>
          <label htmlFor="order-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Order date
          </label>
          <input
            id="order-date"
            type="date"
            value={orderDate}
            onChange={(event) => setOrderDate(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div>
          <label htmlFor="requested-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Requested date
          </label>
          <input
            id="requested-date"
            type="date"
            value={requestedDate}
            onChange={(event) => setRequestedDate(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div className="col-span-4">
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

      <div className="mt-6">
        <SalesOrderLinesEditor
          lines={lines}
          items={items.data?.items ?? []}
          uoms={uoms.data?.items ?? []}
          taxCodes={taxCodes.data?.items ?? []}
          onChange={setLines}
        />
      </div>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit || busy}
        className="mt-6 btn-ink"
      >
        {busy ? "Saving…" : isEdit ? "Save changes" : "Create draft"}
      </button>
    </div>
  );
}
