/**
 * Cash flow statement (STRUCTURE §4), indirect method, over [date_from, date_to]. Always
 * exactly 3 sections in this order: OPERATING, INVESTING, FINANCING (present even if empty).
 * `is_reconciled` (net_change_from_activities == cash_account_movement) is guaranteed by
 * double-entry construction — a false value flags a data-integrity bug, not something the
 * user fixes here.
 */

import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useCashFlowStatement, useFunctionalCurrency } from "@/modules/finance/hooks";
import type { CashFlowCategory } from "@/modules/finance/types";

const SECTION_LABELS: Record<CashFlowCategory, string> = {
  OPERATING: "Operating activities",
  INVESTING: "Investing activities",
  FINANCING: "Financing activities",
};

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function startOfMonth(): string {
  const now = new Date();
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-01`;
}

export function CashFlowStatementPage() {
  const [dateFrom, setDateFrom] = useState(startOfMonth());
  const [dateTo, setDateTo] = useState(today());
  const cashFlow = useCashFlowStatement(dateFrom, dateTo);
  const currency = useFunctionalCurrency();
  const currencyCode = currency.data ?? "—";

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Cash Flow Statement</h1>

      <div className="mt-4 flex items-center gap-4">
        <input
          type="date"
          value={dateFrom}
          onChange={(event) => setDateFrom(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        />
        <span className="text-sm text-ink-muted">to</span>
        <input
          type="date"
          value={dateTo}
          onChange={(event) => setDateTo(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        />
        {cashFlow.data && !cashFlow.data.is_reconciled && (
          <span className="rounded-control bg-danger-tint px-2 py-1 text-xs font-medium text-danger">
            Not reconciled — data integrity issue
          </span>
        )}
      </div>

      {cashFlow.isPending ? (
        <p className="mt-6 text-sm text-ink-muted">Loading…</p>
      ) : (
        cashFlow.data && (
          <div className="mt-6 rounded-card border border-line bg-surface p-4 shadow-card">
            <div className="flex items-center justify-between text-sm">
              <span className="text-ink-muted">Net income</span>
              <span className="tabular-nums text-ink">{formatMoney(cashFlow.data.net_income, currencyCode)}</span>
            </div>

            <table className="mt-3 w-full border-collapse text-[13px]">
              {cashFlow.data.sections.map((section) => (
                <tbody key={section.category}>
                  <tr>
                    <td colSpan={2} className="pt-3 pb-1 mono-caps text-ink-muted">
                      {SECTION_LABELS[section.category]}
                    </td>
                  </tr>
                  {section.lines.length === 0 ? (
                    <tr>
                      <td colSpan={2} className="py-1 pl-3 text-sm text-ink-muted">No activity.</td>
                    </tr>
                  ) : (
                    section.lines.map((line) => (
                      <tr key={line.account_id} className="border-b border-line last:border-b-0">
                        <td className="py-1 pl-3 text-ink">
                          {line.account_code} — {line.account_name}
                        </td>
                        <td className="py-1 text-right tabular-nums text-ink">
                          {formatMoney(line.amount, currencyCode)}
                        </td>
                      </tr>
                    ))
                  )}
                  <tr className="border-b border-line">
                    <td className="py-1 pl-3 text-right text-xs font-medium text-ink-muted">Subtotal</td>
                    <td className="py-1 text-right tabular-nums text-xs font-medium text-ink-muted">
                      {formatMoney(section.subtotal, currencyCode)}
                    </td>
                  </tr>
                </tbody>
              ))}
            </table>

            <div className="mt-4 space-y-1 border-t border-line pt-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-ink">Net change from activities</span>
                <span className="tabular-nums font-semibold text-ink">
                  {formatMoney(cashFlow.data.net_change_from_activities, currencyCode)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-ink-muted">Cash account movement</span>
                <span className="tabular-nums text-ink-muted">
                  {formatMoney(cashFlow.data.cash_account_movement, currencyCode)}
                </span>
              </div>
            </div>
          </div>
        )
      )}
    </div>
  );
}
