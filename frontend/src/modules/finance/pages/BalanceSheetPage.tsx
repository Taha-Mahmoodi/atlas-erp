/**
 * Balance sheet (STRUCTURE §4) as of a date, cumulative from ledger inception (no lower
 * bound — same as trial balance). Retained earnings has no stored ledger account; the backend
 * computes it on the fly and injects it as a synthetic line inside equity_groups (its
 * account_id is a placeholder, not a real Chart-of-Accounts entry). `is_balanced` is the
 * accounting-equation self-check (assets == liabilities + equity), guaranteed by double-entry
 * construction — a false value flags a data bug, not something to fix here.
 */

import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { StatementGroupTable } from "@/modules/finance/components/StatementGroupTable";
import { useBalanceSheet, useFunctionalCurrency } from "@/modules/finance/hooks";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function BalanceSheetPage() {
  const [asOf, setAsOf] = useState(today());
  const balanceSheet = useBalanceSheet(asOf);
  const currency = useFunctionalCurrency();
  const currencyCode = currency.data ?? "—";

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Balance Sheet</h1>

      <div className="mt-4 flex items-center gap-4">
        <input
          type="date"
          value={asOf}
          onChange={(event) => setAsOf(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        />
        {balanceSheet.data && !balanceSheet.data.is_balanced && (
          <span className="rounded-control bg-danger-tint px-2 py-1 text-xs font-medium text-danger">
            Not balanced — data integrity issue
          </span>
        )}
      </div>

      {balanceSheet.isPending ? (
        <p className="mt-6 text-sm text-ink-muted">Loading…</p>
      ) : (
        balanceSheet.data && (
          <div className="mt-6 grid grid-cols-2 gap-4">
            <div className="rounded-card border border-line bg-surface p-4 shadow-card">
              <h2 className="text-xs font-semibold uppercase tracking-[0.02em] text-ink-muted">Assets</h2>
              <StatementGroupTable
                groups={balanceSheet.data.asset_groups}
                total={balanceSheet.data.asset_total}
                totalLabel="Total assets"
                currencyCode={currencyCode}
              />
            </div>
            <div className="space-y-4">
              <div className="rounded-card border border-line bg-surface p-4 shadow-card">
                <h2 className="text-xs font-semibold uppercase tracking-[0.02em] text-ink-muted">Liabilities</h2>
                <StatementGroupTable
                  groups={balanceSheet.data.liability_groups}
                  total={balanceSheet.data.liability_total}
                  totalLabel="Total liabilities"
                  currencyCode={currencyCode}
                />
              </div>
              <div className="rounded-card border border-line bg-surface p-4 shadow-card">
                <h2 className="text-xs font-semibold uppercase tracking-[0.02em] text-ink-muted">Equity</h2>
                <StatementGroupTable
                  groups={balanceSheet.data.equity_groups}
                  total={balanceSheet.data.equity_total}
                  totalLabel="Total equity"
                  currencyCode={currencyCode}
                />
              </div>
            </div>
            <div className="col-span-2 flex items-center justify-between border-t border-line pt-3">
              <span className="text-sm text-ink-muted">
                Assets = Liabilities + Equity ({formatMoney(balanceSheet.data.asset_total, currencyCode)} ={" "}
                {formatMoney(balanceSheet.data.liability_total, currencyCode)} +{" "}
                {formatMoney(balanceSheet.data.equity_total, currencyCode)})
              </span>
            </div>
          </div>
        )
      )}
    </div>
  );
}
