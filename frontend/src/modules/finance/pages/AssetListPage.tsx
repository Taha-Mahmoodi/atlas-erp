/**
 * Fixed assets list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014). Net book
 * value isn't shown here — `AssetRead` doesn't carry it (NBV is never stored, only ever a
 * projection via the asset register report) — see AssetRegisterPage for that view.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatDate, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useAssets } from "@/modules/finance/hooks";
import type { Asset, AssetStatus } from "@/modules/finance/types";

const COLUMNS: DataGridColumn<Asset>[] = [
  { key: "asset_number", header: "Asset #", render: (row) => row.asset_number ?? "(draft)", width: "130px" },
  { key: "name", header: "Name", render: (row) => row.name },
  { key: "acquisition_date", header: "Acquired", render: (row) => formatDate(row.acquisition_date), width: "120px" },
  {
    key: "acquisition_cost",
    header: "Cost",
    align: "right",
    render: (row) => formatMoney(row.acquisition_cost, row.currency_code),
    width: "130px",
  },
  { key: "depreciation_method", header: "Method", render: (row) => row.depreciation_method.replace("_", " "), width: "150px" },
  { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "140px" },
];

export function AssetListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("finance.asset.manage");
  const [status, setStatus] = useState<AssetStatus | "">("");

  const assets = useAssets(status ? { status } : {});
  const rows = assets.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Fixed Assets</h1>
        {canManage && (
          <Link
            to="/finance/assets/new"
            className="btn-ink"
          >
            New asset
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as AssetStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="ACTIVE">Active</option>
          <option value="FULLY_DEPRECIATED">Fully depreciated</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/finance/assets/$assetId", params: { assetId: row.id } })}
          loading={assets.isPending}
          emptyMessage="No fixed assets yet."
          hasMore={assets.hasNextPage}
          onLoadMore={() => void assets.fetchNextPage()}
          loadingMore={assets.isFetchingNextPage}
          label="Fixed assets"
        />
      </div>
    </div>
  );
}
