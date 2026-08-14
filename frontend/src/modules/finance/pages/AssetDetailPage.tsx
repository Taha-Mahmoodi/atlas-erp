/**
 * Asset detail (STRUCTURE §4): view + the Activate action. Activation claims the gapless
 * AST-##### number and makes the asset depreciation-eligible; `capitalize` is a one-time,
 * one-way choice made here (no separate call to capitalize later) — true posts the
 * acquisition journal, false skips it (asset already reflected via an opening-balance import).
 */

import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDate, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useAccountLookup, useActivateAsset, useAsset } from "@/modules/finance/hooks";

export function AssetDetailPage() {
  const { assetId } = useParams({ strict: false });
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("finance.asset.manage");
  const asset = useAsset(assetId);
  const accounts = useAccountLookup();
  const activateAsset = useActivateAsset(assetId ?? "");
  const [capitalize, setCapitalize] = useState(true);
  const [error, setError] = useState<string | null>(null);

  if (asset.isPending || !asset.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = asset.data;
  const accountLabel = (accountId: string) => {
    const account = accounts.data?.items.find((a) => a.id === accountId);
    return account ? `${account.code} — ${account.name}` : accountId;
  };

  const activate = async () => {
    setError(null);
    try {
      await activateAsset.mutateAsync({ capitalize });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to activate the asset."));
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.asset_number ?? data.name}</h1>
        {canManage && data.status === "DRAFT" && (
          <Link
            to="/finance/assets/$assetId/edit"
            params={{ assetId: data.id }}
            className="btn-chip"
          >
            Edit
          </Link>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <dl className="mt-6 grid grid-cols-2 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Name</dt>
          <dd className="text-ink">{data.name}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Status</dt>
          <dd className="text-ink">{data.status.replace("_", " ")}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Acquisition date</dt>
          <dd className="text-ink">{formatDate(data.acquisition_date)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Acquisition cost</dt>
          <dd className="tabular-nums text-ink">{formatMoney(data.acquisition_cost, data.currency_code)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Salvage value</dt>
          <dd className="tabular-nums text-ink">{formatMoney(data.salvage_value, data.currency_code)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Useful life</dt>
          <dd className="text-ink">{data.useful_life_months} months</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Depreciation method</dt>
          <dd className="text-ink">
            {data.depreciation_method.replace("_", " ")}
            {data.declining_rate_percent ? ` (${data.declining_rate_percent}%/yr)` : ""}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Asset account</dt>
          <dd className="text-ink">{accountLabel(data.asset_account_id)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Accumulated depreciation account</dt>
          <dd className="text-ink">{accountLabel(data.accumulated_depreciation_account_id)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Depreciation expense account</dt>
          <dd className="text-ink">{accountLabel(data.depreciation_expense_account_id)}</dd>
        </div>
      </dl>

      {canManage && data.status === "DRAFT" && (
        <div className="mt-6 rounded-card border border-line bg-surface p-4 shadow-card">
          <h2 className="text-sm font-semibold text-ink">Activate</h2>
          <label className="mt-2 flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={capitalize}
              onChange={(event) => setCapitalize(event.target.checked)}
            />
            Post the acquisition journal (uncheck if this asset is already reflected on the
            books via an opening-balance import)
          </label>
          <button
            type="button"
            onClick={() => void activate()}
            disabled={activateAsset.isPending}
            className="mt-3 btn-ink"
          >
            {activateAsset.isPending ? "Activating…" : "Activate"}
          </button>
        </div>
      )}
    </div>
  );
}
