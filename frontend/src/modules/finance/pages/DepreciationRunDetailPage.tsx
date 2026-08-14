/**
 * Depreciation run detail (STRUCTURE §4): the run header plus its per-asset entries.
 * `accumulated_after`/`nbv_after` are audit-trail snapshots for this run only — the asset
 * register report is the authoritative aggregate NBV view, not this list.
 */

import { useParams } from "@tanstack/react-router";

import { formatDate, formatMoney } from "@/lib/format";
import {
  useAssets,
  useDepreciationEntries,
  useDepreciationRun,
  useFunctionalCurrency,
} from "@/modules/finance/hooks";

export function DepreciationRunDetailPage() {
  const { runId } = useParams({ strict: false });
  const run = useDepreciationRun(runId);
  const entries = useDepreciationEntries(runId);
  const assets = useAssets({ limit: 200 });
  const currency = useFunctionalCurrency();
  const currencyCode = currency.data ?? "—";

  if (run.isPending || !run.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = run.data;
  const assetLabel = (assetId: string) => {
    const asset = assets.data?.pages.flatMap((page) => page.items).find((a) => a.id === assetId);
    return asset ? (asset.asset_number ?? asset.name) : assetId;
  };

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.run_number ?? "Depreciation run"}</h1>

      <dl className="mt-6 grid grid-cols-3 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Run date</dt>
          <dd className="text-ink">{formatDate(data.run_date)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Status</dt>
          <dd className="text-ink">{data.status}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Assets</dt>
          <dd className="text-ink">{data.asset_count}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Total amount</dt>
          <dd className="tabular-nums text-ink">{formatMoney(data.total_amount, currencyCode)}</dd>
        </div>
      </dl>

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-2 pr-2">Asset</th>
            <th className="py-2 pr-2 text-right">Amount</th>
            <th className="py-2 pr-2 text-right">Accumulated after</th>
            <th className="py-2 pr-2 text-right">NBV after</th>
          </tr>
        </thead>
        <tbody>
          {(entries.data?.items ?? []).map((entry) => (
            <tr key={entry.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{assetLabel(entry.asset_id)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums text-ink">
                {formatMoney(entry.amount, currencyCode)}
              </td>
              <td className="py-1.5 pr-2 text-right tabular-nums text-ink-muted">
                {formatMoney(entry.accumulated_after, currencyCode)}
              </td>
              <td className="py-1.5 pr-2 text-right tabular-nums text-ink-muted">
                {formatMoney(entry.nbv_after, currencyCode)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
