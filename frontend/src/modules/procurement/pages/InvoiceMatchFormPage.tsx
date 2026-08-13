/**
 * Create a 3-way invoice match against a purchase order (STRUCTURE §4). Only POs with a
 * received-not-yet-billed quantity (PARTIALLY_RECEIVED/RECEIVED) are offered. One row per PO
 * line lets the operator enter the matched quantity and unit price from the vendor's invoice,
 * plus an optional specific goods-receipt line — picking one changes how the backend computes
 * quantity variance (see types.ts): without it, a naive comparison could flag an ordinary
 * partial invoice as an exception. po_unit_cost/variances/within_tolerance are NOT entered
 * here — the backend computes them at create time.
 */

import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatQuantity } from "@/lib/format";
import { useTaxCodes } from "@/modules/finance/hooks";
import {
  useCreateInvoiceMatch,
  useGoodsReceiptLinesForPurchaseOrder,
  usePurchaseOrder,
  usePurchaseOrders,
} from "@/modules/procurement/hooks";
import type { InvoiceMatchLineCreate } from "@/modules/procurement/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

const MATCHABLE_STATUSES = new Set(["PARTIALLY_RECEIVED", "RECEIVED"]);

export function InvoiceMatchFormPage() {
  const navigate = useNavigate();
  const orders = usePurchaseOrders();
  const matchableOrders = (orders.data?.pages.flatMap((page) => page.items) ?? []).filter((order) =>
    MATCHABLE_STATUSES.has(order.status),
  );
  const taxCodes = useTaxCodes();

  const [purchaseOrderId, setPurchaseOrderId] = useState("");
  const [vendorInvoiceRef, setVendorInvoiceRef] = useState("");
  const [invoiceDate, setInvoiceDate] = useState(today());
  const [taxCodeId, setTaxCodeId] = useState("");
  const [notes, setNotes] = useState("");
  const [lineInputs, setLineInputs] = useState<
    Record<string, Partial<{ quantity: string; unitPrice: string; goodsReceiptLineId: string }>>
  >({});
  const [error, setError] = useState<string | null>(null);

  const order = usePurchaseOrder(purchaseOrderId || undefined);
  const grLines = useGoodsReceiptLinesForPurchaseOrder(purchaseOrderId || undefined);
  const createInvoiceMatch = useCreateInvoiceMatch();

  const setLineInput = (
    lineId: string,
    patch: Partial<{ quantity: string; unitPrice: string; goodsReceiptLineId: string }>,
  ) => {
    setLineInputs((prev) => ({
      ...prev,
      [lineId]: { ...prev[lineId], ...patch },
    }));
  };

  const lines: InvoiceMatchLineCreate[] = (order.data?.lines ?? [])
    .map((line) => {
      const input = lineInputs[line.id];
      return {
        purchase_order_line_id: line.id,
        goods_receipt_line_id: input?.goodsReceiptLineId || null,
        matched_quantity: input?.quantity ?? "",
        unit_price: input?.unitPrice ?? String(line.unit_cost),
      };
    })
    .filter((line) => (Number(line.matched_quantity) || 0) > 0 && (Number(line.unit_price) || 0) > 0);

  const canSubmit = Boolean(purchaseOrderId) && lines.length > 0;

  const submit = async () => {
    setError(null);
    try {
      const match = await createInvoiceMatch.mutateAsync({
        purchase_order_id: purchaseOrderId,
        vendor_invoice_ref: vendorInvoiceRef || null,
        invoice_date: invoiceDate || null,
        tax_code_id: taxCodeId || null,
        notes: notes || null,
        lines,
      });
      void navigate({ to: "/procurement/invoice-matches/$invoiceMatchId", params: { invoiceMatchId: match.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the invoice match."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-xl font-semibold text-ink">New invoice match</h1>
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
            {matchableOrders.map((po) => (
              <option key={po.id} value={po.id}>
                {po.po_number}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="invoice-ref" className="mb-1 block text-xs font-medium text-ink-muted">
            Vendor's invoice ref
          </label>
          <input
            id="invoice-ref"
            type="text"
            value={vendorInvoiceRef}
            onChange={(event) => setVendorInvoiceRef(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div>
          <label htmlFor="invoice-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Invoice date
          </label>
          <input
            id="invoice-date"
            type="date"
            value={invoiceDate}
            onChange={(event) => setInvoiceDate(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div>
          <label htmlFor="tax-code" className="mb-1 block text-xs font-medium text-ink-muted">
            Tax code
          </label>
          <select
            id="tax-code"
            value={taxCodeId}
            onChange={(event) => setTaxCodeId(event.target.value)}
            className={CONTROL}
          >
            <option value="">None</option>
            {(taxCodes.data?.items ?? []).map((tax) => (
              <option key={tax.id} value={tax.id}>
                {tax.code} ({tax.rate_percent}%)
              </option>
            ))}
          </select>
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

      {purchaseOrderId && (
        <div className="mt-6">
          {order.isPending ? (
            <p className="text-sm text-ink-muted">Loading purchase order lines…</p>
          ) : (
            <table className="w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
                  <th className="py-2 pr-2">Line</th>
                  <th className="py-2 pr-2 text-right">Received</th>
                  <th className="w-24 py-2 pr-2 text-right">Matched qty</th>
                  <th className="w-24 py-2 pr-2 text-right">Unit price</th>
                  <th className="py-2 pr-2">Against receipt (optional)</th>
                </tr>
              </thead>
              <tbody>
                {(order.data?.lines ?? []).map((line) => {
                  const input = lineInputs[line.id];
                  const linesForThisPoLine = (grLines.data ?? []).filter(
                    (grLine) => grLine.purchase_order_line_id === line.id,
                  );
                  return (
                    <tr key={line.id} className="border-b border-line last:border-b-0">
                      <td className="py-1.5 pr-2 text-ink">Line {line.line_number}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.received_quantity)}</td>
                      <td className="py-1.5 pr-2">
                        <input
                          type="number"
                          step="0.000001"
                          value={input?.quantity ?? ""}
                          onChange={(event) => setLineInput(line.id, { quantity: event.target.value })}
                          className="w-full rounded-control border border-line bg-surface px-2 py-1 text-right text-sm tabular-nums"
                        />
                      </td>
                      <td className="py-1.5 pr-2">
                        <input
                          type="number"
                          step="0.01"
                          value={input?.unitPrice ?? line.unit_cost}
                          onChange={(event) => setLineInput(line.id, { unitPrice: event.target.value })}
                          className="w-full rounded-control border border-line bg-surface px-2 py-1 text-right text-sm tabular-nums"
                        />
                      </td>
                      <td className="py-1.5 pr-2">
                        <select
                          value={input?.goodsReceiptLineId ?? ""}
                          onChange={(event) => setLineInput(line.id, { goodsReceiptLineId: event.target.value })}
                          className="w-full rounded-control border border-line bg-surface px-2 py-1 text-sm"
                        >
                          <option value="">Not specified</option>
                          {linesForThisPoLine.map((grLine) => (
                            <option key={grLine.id} value={grLine.id}>
                              {grLine.gr_number} — {formatQuantity(grLine.received_quantity)}
                            </option>
                          ))}
                        </select>
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
        disabled={!canSubmit || createInvoiceMatch.isPending}
        className="mt-6 rounded-control bg-primary px-4 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
      >
        {createInvoiceMatch.isPending ? "Creating…" : "Create match"}
      </button>
    </div>
  );
}
