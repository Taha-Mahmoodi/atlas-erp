/**
 * The invoice match workbench (STRUCTURE §4): review per-line price/quantity variance against
 * tolerance, post (blocked while EXCEPTION — override first), or cancel. Posting publishes
 * InvoiceMatched: finance creates+posts the AP vendor bill in the same transaction — there is
 * no "create bill" button here; the resulting bill is only visible via finance's own
 * VendorBillListPage/VendorBillDetailPage (D-042: no vendor_bill_id FK by design).
 */

import { useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatMoney, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useItemLookup } from "@/modules/inventory/hooks";
import {
  useCancelInvoiceMatch,
  useInvoiceMatch,
  useOverrideInvoiceMatch,
  usePostInvoiceMatch,
  useVendorLookup,
} from "@/modules/procurement/hooks";

export function InvoiceMatchDetailPage() {
  const { invoiceMatchId } = useParams({ strict: false });
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("procurement.invoice_match.manage");
  const canPost = (me.data?.permissions ?? []).includes("procurement.invoice_match.post");

  const match = useInvoiceMatch(invoiceMatchId);
  const items = useItemLookup();
  const vendors = useVendorLookup();
  const postMatch = usePostInvoiceMatch(invoiceMatchId ?? "");
  const overrideMatch = useOverrideInvoiceMatch(invoiceMatchId ?? "");
  const cancelMatch = useCancelInvoiceMatch(invoiceMatchId ?? "");

  const [error, setError] = useState<string | null>(null);

  if (match.isPending || !match.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = match.data;
  const isException = data.status === "EXCEPTION";
  const canPostNow = (data.status === "MATCHED" || data.status === "DRAFT") && canPost;
  const canCancel = data.status !== "POSTED" && data.status !== "CANCELLED";

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };
  const vendorLabel = (id: string) => {
    const vendor = vendors.data?.items.find((v) => v.id === id);
    return vendor ? `${vendor.vendor_code} — ${vendor.name}` : id;
  };

  const post = async () => {
    setError(null);
    try {
      await postMatch.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to post the invoice match."));
    }
  };

  const override = async () => {
    setError(null);
    try {
      await overrideMatch.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to override the exception."));
    }
  };

  const cancel = async () => {
    setError(null);
    try {
      await cancelMatch.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to cancel the invoice match."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">{data.match_number}</h1>
        <div className="flex gap-2">
          {canCancel && canManage && (
            <button
              type="button"
              onClick={() => void cancel()}
              disabled={cancelMatch.isPending}
              className="rounded-control border border-line px-3 py-1.5 text-sm font-medium text-ink transition-colors duration-150 hover:border-danger hover:text-danger disabled:cursor-not-allowed disabled:opacity-45"
            >
              Cancel
            </button>
          )}
          {isException && canManage && (
            <button
              type="button"
              onClick={() => void override()}
              disabled={overrideMatch.isPending}
              className="rounded-control border border-line px-3 py-1.5 text-sm font-medium text-ink transition-colors duration-150 hover:border-primary disabled:cursor-not-allowed disabled:opacity-45"
            >
              {overrideMatch.isPending ? "Overriding…" : "Override exception"}
            </button>
          )}
          {canPostNow && (
            <button
              type="button"
              onClick={() => void post()}
              disabled={postMatch.isPending}
              className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
            >
              {postMatch.isPending ? "Posting…" : "Post"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      {isException && (
        <p className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          One or more lines are outside the configured price/quantity tolerance. Posting is blocked
          until the exception is overridden.
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
          <dt className="text-xs text-ink-muted">Vendor invoice ref</dt>
          <dd className="text-ink">{data.vendor_invoice_ref ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Total</dt>
          <dd className="text-ink">{formatMoney(data.total_amount, data.currency_code)}</dd>
        </div>
      </dl>

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
            <th className="py-2 pr-2">Item</th>
            <th className="py-2 pr-2 text-right">Matched qty</th>
            <th className="py-2 pr-2 text-right">Unit price</th>
            <th className="py-2 pr-2 text-right">PO unit cost</th>
            <th className="py-2 pr-2 text-right">Price var.</th>
            <th className="py-2 pr-2 text-right">Qty var.</th>
            <th className="py-2 pr-2">Tolerance</th>
          </tr>
        </thead>
        <tbody>
          {data.lines.map((line) => (
            <tr key={line.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{itemLabel(line.item_id)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.matched_quantity)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.unit_price, data.currency_code)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.po_unit_cost, data.currency_code)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.price_variance, data.currency_code)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.quantity_variance)}</td>
              <td className="py-1.5 pr-2">
                <span
                  className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${
                    line.within_tolerance ? "bg-success-tint text-success" : "bg-danger-tint text-danger"
                  }`}
                >
                  {line.within_tolerance ? "OK" : "Exception"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
