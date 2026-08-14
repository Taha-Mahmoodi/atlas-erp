/**
 * Profit & loss / income statement (STRUCTURE §4) over [date_from, date_to]. Revenue and
 * expense totals are already presentation-signed positive by the backend — no sign-flipping
 * needed here. net_income = revenue_total - expense_total (positive = profit).
 */

import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { StatementGroupTable } from "@/modules/finance/components/StatementGroupTable";
import { useFunctionalCurrency, useProfitAndLoss } from "@/modules/finance/hooks";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function startOfMonth(): string {
  const now = new Date();
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-01`;
}

export function ProfitAndLossPage() {
  const [dateFrom, setDateFrom] = useState(startOfMonth());
  const [dateTo, setDateTo] = useState(today());
  const pnl = useProfitAndLoss(dateFrom, dateTo);
  const currency = useFunctionalCurrency();
  const currencyCode = currency.data ?? "—";

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/finance">Finance</Link> / <span className="text-ink">Profit &amp; Loss</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">Profit &amp; Loss</h1>
      </header>

      <div className="flex items-center gap-4">
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
      </div>

      {pnl.isPending ? (
        <p className="mt-6 text-[13px] text-ink-muted">Loading…</p>
      ) : (
        pnl.data && (
          <div className="mt-6 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
            <h2 className="mb-3.5 mono-caps text-ink-muted">Revenue</h2>
            <StatementGroupTable
              groups={pnl.data.revenue_groups}
              total={pnl.data.revenue_total}
              totalLabel="Total revenue"
              currencyCode={currencyCode}
            />

            <h2 className="mb-3.5 mt-6 mono-caps text-ink-muted">Expenses</h2>
            <StatementGroupTable
              groups={pnl.data.expense_groups}
              total={pnl.data.expense_total}
              totalLabel="Total expenses"
              currencyCode={currencyCode}
            />

            <div className="mt-6 flex items-center justify-between border-t border-line pt-3">
              <span className="text-sm font-semibold text-ink">Net income</span>
              <span
                className={`text-sm font-semibold tabular-nums ${Number(pnl.data.net_income) < 0 ? "text-danger" : "text-success"}`}
              >
                {formatMoney(pnl.data.net_income, currencyCode)}
              </span>
            </div>
          </div>
        )
      )}
    </div>
  );
}
