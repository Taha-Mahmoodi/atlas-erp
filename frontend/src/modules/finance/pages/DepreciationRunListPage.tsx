/**
 * Depreciation runs list (STRUCTURE §4). Keyset-paginated (D-014); row click opens the run's
 * per-asset entries.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { formatDate, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useDepreciationRuns, useFunctionalCurrency } from "@/modules/finance/hooks";
import type { DepreciationRun } from "@/modules/finance/types";

export function DepreciationRunListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canRun = (me.data?.permissions ?? []).includes("finance.depreciation.run");
  const runs = useDepreciationRuns();
  const currency = useFunctionalCurrency();
  const rows = runs.data?.pages.flatMap((page) => page.items) ?? [];

  const columns: DataGridColumn<DepreciationRun>[] = [
    { key: "run_number", header: "Run #", render: (row) => row.run_number ?? "(draft)", width: "140px" },
    { key: "run_date", header: "Run date", render: (row) => formatDate(row.run_date), width: "120px" },
    { key: "asset_count", header: "Assets", align: "right", render: (row) => String(row.asset_count), width: "90px" },
    {
      key: "total_amount",
      header: "Total",
      align: "right",
      render: (row) => formatMoney(row.total_amount, currency.data ?? "—"),
      width: "130px",
    },
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/finance">Finance</Link> / <span className="text-ink">Depreciation Runs</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Depreciation Runs</h1>
          <div className="flex items-center gap-2.5">
            {canRun && (
              <Link
                to="/finance/depreciation-runs/new"
                className="btn-ink"
              >
                Run depreciation
              </Link>
            )}
          </div>
        </div>
      </header>

      <div>
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/finance/depreciation-runs/$runId", params: { runId: row.id } })}
          loading={runs.isPending}
          emptyMessage="No depreciation runs yet."
          hasMore={runs.hasNextPage}
          onLoadMore={() => void runs.fetchNextPage()}
          loadingMore={runs.isFetchingNextPage}
          label="Depreciation runs"
        />
      </div>
    </div>
  );
}
