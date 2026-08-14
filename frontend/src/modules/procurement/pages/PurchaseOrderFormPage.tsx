/**
 * Create a purchase order directly (STRUCTURE §4). No edit path — like vendor bills, POs are
 * create-then-work only per the backend surface (no PATCH endpoint). POs sourced from an
 * approved requisition or a quoted RFQ are created via those documents' own convert actions,
 * not this form.
 */

import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useTaxCodes } from "@/modules/finance/hooks";
import { useItemOptions, useUomOptions } from "@/modules/inventory/hooks";
import { PurchaseOrderLinesEditor } from "@/modules/procurement/components/PurchaseOrderLinesEditor";
import { useCreatePurchaseOrder, useVendorOptions } from "@/modules/procurement/hooks";
import type { PurchaseOrderLineCreate } from "@/modules/procurement/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function PurchaseOrderFormPage() {
  const navigate = useNavigate();
  const vendors = useVendorOptions();
  const items = useItemOptions();
  const uoms = useUomOptions();
  const taxCodes = useTaxCodes();
  const createPurchaseOrder = useCreatePurchaseOrder();

  const [vendorId, setVendorId] = useState("");
  const [currencyCode, setCurrencyCode] = useState("USD");
  const [orderDate, setOrderDate] = useState(today());
  const [expectedDate, setExpectedDate] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<PurchaseOrderLineCreate[]>([
    { item_id: "", quantity: "", uom_id: "", unit_cost: "" },
  ]);
  const [error, setError] = useState<string | null>(null);

  const validLines = lines.filter(
    (line) => line.item_id && line.uom_id && (Number(line.quantity) || 0) > 0 && (Number(line.unit_cost) || 0) > 0,
  );
  const canSubmit = Boolean(vendorId) && validLines.length > 0;

  const submit = async () => {
    setError(null);
    try {
      const po = await createPurchaseOrder.mutateAsync({
        vendor_id: vendorId,
        currency_code: currencyCode,
        order_date: orderDate || null,
        expected_date: expectedDate || null,
        notes: notes || null,
        lines: validLines,
      });
      void navigate({ to: "/procurement/purchase-orders/$purchaseOrderId", params: { purchaseOrderId: po.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the purchase order."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">New purchase order</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 grid grid-cols-3 gap-4">
        <div>
          <label htmlFor="vendor" className="mb-1 block text-xs font-medium text-ink-muted">
            Vendor
          </label>
          <select
            id="vendor"
            value={vendorId}
            onChange={(event) => setVendorId(event.target.value)}
            className={CONTROL}
          >
            <option value="">Select vendor</option>
            {(vendors.data?.items ?? []).map((vendor) => (
              <option key={vendor.id} value={vendor.id}>
                {vendor.vendor_code} — {vendor.name}
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
          <label htmlFor="expected-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Expected date
          </label>
          <input
            id="expected-date"
            type="date"
            value={expectedDate}
            onChange={(event) => setExpectedDate(event.target.value)}
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

      <div className="mt-6">
        <PurchaseOrderLinesEditor
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
        disabled={!canSubmit || createPurchaseOrder.isPending}
        className="mt-6 btn-ink"
      >
        {createPurchaseOrder.isPending ? "Creating…" : "Create draft"}
      </button>
    </div>
  );
}
