/**
 * Vendor bill detail (STRUCTURE §4): header, lines, and the Post action gated by status AND
 * permission. No reverse action here — the backend exposes no /vendor-bills/{id}/reverse
 * endpoint (a bill's REVERSED status follows from its journal entry being reversed
 * elsewhere, not a bill-level action).
 */

import { useParams } from "@tanstack/react-router";

import { ApiError } from "@/lib/apiClient";
import { formatDate, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useAccountLookup, useVendorBill, usePostVendorBill } from "@/modules/finance/hooks";
import { useState } from "react";

export function VendorBillDetailPage() {
  const { billId } = useParams({ strict: false });
  const me = useMe();
  const bill = useVendorBill(billId);
  const accounts = useAccountLookup();
  const postBill = usePostVendorBill(billId ?? "");
  const [error, setError] = useState<string | null>(null);

  if (bill.isPending || !bill.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = bill.data;
  const canPost = (me.data?.permissions ?? []).includes("finance.ap.manage");
  const accountLabel = (accountId: string) => {
    const account = accounts.data?.items.find((a) => a.id === accountId);
    return account ? `${account.code} — ${account.name}` : accountId;
  };

  const post = async () => {
    setError(null);
    try {
      await postBill.mutateAsync();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to post the bill.");
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.bill_number ?? "Draft bill"}</h1>
        {data.status === "DRAFT" && canPost && (
          <button
            type="button"
            onClick={() => void post()}
            disabled={postBill.isPending}
            className="btn-ink"
          >
            {postBill.isPending ? "Posting…" : "Post bill"}
          </button>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <dl className="mt-6 grid grid-cols-3 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Vendor</dt>
          <dd className="text-ink">{data.partner_name}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Status</dt>
          <dd className="text-ink">{data.status}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Vendor's reference</dt>
          <dd className="text-ink">{data.bill_external_ref ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Bill date</dt>
          <dd className="text-ink">{formatDate(data.bill_date)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Due date</dt>
          <dd className="text-ink">{formatDate(data.due_date)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Open amount</dt>
          <dd className="tabular-nums text-ink">{formatMoney(data.open_amount, data.currency_code)}</dd>
        </div>
      </dl>

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-2 pr-2">Account</th>
            <th className="py-2 pr-2">Description</th>
            <th className="py-2 pr-2 text-right">Net</th>
            <th className="py-2 pr-2 text-right">Tax</th>
          </tr>
        </thead>
        <tbody>
          {data.lines.map((line) => (
            <tr key={line.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{accountLabel(line.account_id)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{line.description ?? "—"}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums text-ink">
                {formatMoney(line.net_amount, data.currency_code)}
              </td>
              <td className="py-1.5 pr-2 text-right tabular-nums text-ink">
                {Number(line.tax_amount) > 0 ? formatMoney(line.tax_amount, data.currency_code) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={2} className="pt-2 text-right text-xs font-medium text-ink-muted">
              Gross total
            </td>
            <td colSpan={2} className="pt-2 text-right tabular-nums font-medium text-ink">
              {formatMoney(data.gross_amount, data.currency_code)}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
