/**
 * Run a dunning pass (STRUCTURE §4): advances the reminder level on overdue open invoices as
 * of a date (optionally scoped to one customer) and shows the notice list the run produced.
 * Posts no journal — a pure collections-state update, so there's no "detail" to navigate to
 * beyond this run's own result.
 */

import { useState } from "react";

import { ApiError } from "@/lib/apiClient";
import { formatDate, formatMoney } from "@/lib/format";
import { useRunDunning } from "@/modules/finance/hooks";
import type { DunningRunResult } from "@/modules/finance/types";
import { useCustomerOptions } from "@/modules/sales/hooks";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function DunningRunPage() {
  const customers = useCustomerOptions();
  const runDunning = useRunDunning();

  const [asOf, setAsOf] = useState(today());
  const [partnerId, setPartnerId] = useState("");
  const [result, setResult] = useState<DunningRunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setError(null);
    try {
      const outcome = await runDunning.mutateAsync({
        as_of: asOf,
        ...(partnerId ? { partner_id: partnerId } : {}),
      });
      setResult(outcome);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to run dunning.");
    }
  };

  return (
    <div>
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Dunning Run</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-4 flex items-center gap-4">
        <input
          type="date"
          value={asOf}
          onChange={(event) => setAsOf(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        />
        <select
          value={partnerId}
          onChange={(event) => setPartnerId(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All customers</option>
          {(customers.data?.items ?? []).map((customer) => (
            <option key={customer.id} value={customer.id}>
              {customer.customer_code} — {customer.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => void run()}
          disabled={runDunning.isPending}
          className="btn-ink"
        >
          {runDunning.isPending ? "Running…" : "Run dunning"}
        </button>
      </div>

      {result && (
        <div className="mt-6 overflow-x-auto rounded-card border border-line bg-surface shadow-card">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-line bg-panel text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
                <th className="px-3 py-2">Customer</th>
                <th className="px-3 py-2">Invoice</th>
                <th className="px-3 py-2 text-right">Open amount</th>
                <th className="px-3 py-2">Due date</th>
                <th className="px-3 py-2 text-right">Days overdue</th>
                <th className="px-3 py-2 text-right">Level</th>
              </tr>
            </thead>
            <tbody>
              {result.notices.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-sm text-ink-muted">
                    No invoices needed a dunning-level increase as of this date.
                  </td>
                </tr>
              ) : (
                result.notices.map((notice) => (
                  <tr key={notice.invoice_id} className="border-b border-line last:border-b-0">
                    <td className="px-3 py-1.5 text-ink">{notice.partner_name}</td>
                    <td className="px-3 py-1.5 text-ink-muted">{notice.invoice_number}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-ink">
                      {formatMoney(notice.open_amount, notice.currency_code)}
                    </td>
                    <td className="px-3 py-1.5 text-ink-muted">{formatDate(notice.due_date)}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-ink">{notice.days_overdue}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-ink">
                      {notice.previous_level} → {notice.new_level}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
