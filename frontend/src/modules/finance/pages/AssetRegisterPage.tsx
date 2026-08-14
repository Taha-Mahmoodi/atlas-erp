/**
 * Asset register report (STRUCTURE §4): every non-draft asset's net book value as of a date.
 * NBV is never stored — this report is the authoritative, recomputed-on-read aggregate view
 * (D-021 "Universal Journal is truth" pattern, same as the financial statements).
 */

import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useAssetRegister } from "@/modules/finance/hooks";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function AssetRegisterPage() {
  const [asOf, setAsOf] = useState(today());
  const register = useAssetRegister(asOf);

  return (
    <div>
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Asset Register</h1>

      <div className="mt-4">
        <input
          type="date"
          value={asOf}
          onChange={(event) => setAsOf(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        />
      </div>

      <div className="mt-4 overflow-x-auto rounded-card border border-line bg-surface shadow-card">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-line text-left mono-caps text-ink-muted">
              <th className="px-3 py-2">Asset #</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2 text-right">Cost</th>
              <th className="px-3 py-2 text-right">Accumulated depreciation</th>
              <th className="px-3 py-2 text-right">Net book value</th>
            </tr>
          </thead>
          <tbody>
            {register.isPending ? (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-sm text-ink-muted">
                  Loading…
                </td>
              </tr>
            ) : (register.data?.items ?? []).length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-sm text-ink-muted">
                  No activated assets as of this date.
                </td>
              </tr>
            ) : (
              register.data?.items.map((row) => (
                <tr key={row.asset_id} className="border-b border-line last:border-b-0">
                  <td className="px-3 py-1.5 text-ink">{row.asset_number ?? "—"}</td>
                  <td className="px-3 py-1.5 text-ink">{row.name}</td>
                  <td className="px-3 py-1.5 text-ink-muted">{row.status.replace("_", " ")}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {formatMoney(row.acquisition_cost, row.currency_code)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums">
                    {formatMoney(row.accumulated_depreciation, row.currency_code)}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-medium">
                    {formatMoney(row.net_book_value, row.currency_code)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
