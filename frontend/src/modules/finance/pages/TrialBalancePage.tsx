/**
 * Trial balance (STRUCTURE §4): every account's net debit/credit as of a date, full history
 * (no lower bound — D-021 the universal journal is append-only from ledger inception). A pure
 * projection — the `is_balanced` self-check is guaranteed true by double-entry construction;
 * a false value would flag a data-integrity bug, not something the user fixes here.
 */

import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useFunctionalCurrency, useTrialBalance } from "@/modules/finance/hooks";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function TrialBalancePage() {
  const [asOf, setAsOf] = useState(today());
  const trialBalance = useTrialBalance(asOf);
  const currency = useFunctionalCurrency();

  return (
    <div>
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Trial Balance</h1>

      <div className="mt-4 flex items-center gap-4">
        <input
          type="date"
          value={asOf}
          onChange={(event) => setAsOf(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        />
        {trialBalance.data && !trialBalance.data.is_balanced && (
          <span className="rounded-control bg-danger-tint px-2 py-1 text-xs font-medium text-danger">
            Not balanced — data integrity issue
          </span>
        )}
      </div>

      <div className="mt-4 overflow-x-auto rounded-card border border-line bg-surface shadow-card">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-line bg-panel text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
              <th className="px-3 py-2">Account</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2 text-right">Debit</th>
              <th className="px-3 py-2 text-right">Credit</th>
            </tr>
          </thead>
          <tbody>
            {trialBalance.isPending ? (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-sm text-ink-muted">
                  Loading…
                </td>
              </tr>
            ) : (trialBalance.data?.rows ?? []).length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-sm text-ink-muted">
                  No posted activity as of this date.
                </td>
              </tr>
            ) : (
              trialBalance.data?.rows.map((row) => (
                <tr key={row.account_id} className="border-b border-line last:border-b-0">
                  <td className="px-3 py-1.5 text-ink">
                    {row.account_code} — {row.account_name}
                  </td>
                  <td className="px-3 py-1.5 text-ink-muted">{row.account_type}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {Number(row.debit) > 0 ? formatMoney(row.debit, currency.data ?? "—") : "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {Number(row.credit) > 0 ? formatMoney(row.credit, currency.data ?? "—") : "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
          {trialBalance.data && trialBalance.data.rows.length > 0 && (
            <tfoot>
              <tr className="border-t border-line bg-panel font-medium">
                <td colSpan={2} className="px-3 py-2 text-ink">Total</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMoney(trialBalance.data.total_debit, currency.data ?? "—")}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatMoney(trialBalance.data.total_credit, currency.data ?? "—")}
                </td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}
