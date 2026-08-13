/**
 * MRP runs list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014); row click
 * opens the run's results (planned orders + rough capacity). New runs submit as background
 * jobs from the form page (D-049).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useMrpRuns } from "@/modules/manufacturing/hooks";
import type { MrpRun, MrpRunStatus } from "@/modules/manufacturing/types";

const STATUS_TONE: Record<MrpRunStatus, string> = {
  RUNNING: "bg-warn-tint text-warn",
  COMPLETED: "bg-success-tint text-success",
  FAILED: "bg-danger-tint text-danger",
};

export function RunStatusChip({ status }: { status: MrpRunStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

const COLUMNS: DataGridColumn<MrpRun>[] = [
  { key: "run_number", header: "Run", render: (row) => row.run_number, width: "140px" },
  { key: "run_date", header: "Run date", render: (row) => row.run_date, width: "110px" },
  {
    key: "horizon_days",
    header: "Horizon (days)",
    align: "right",
    render: (row) => String(row.horizon_days),
    width: "120px",
  },
  {
    key: "planned_make_count",
    header: "Make",
    align: "right",
    render: (row) => String(row.planned_make_count),
    width: "80px",
  },
  {
    key: "planned_buy_count",
    header: "Buy",
    align: "right",
    render: (row) => String(row.planned_buy_count),
    width: "80px",
  },
  { key: "status", header: "Status", render: (row) => <RunStatusChip status={row.status} />, width: "110px" },
];

export function MrpRunListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canRun = (me.data?.permissions ?? []).includes("manufacturing.mrp.run");
  const [status, setStatus] = useState<MrpRunStatus | "">("");

  const runs = useMrpRuns(status ? { status } : {});
  const rows = runs.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">MRP Runs</h1>
        {canRun && (
          <Link
            to="/manufacturing/mrp/runs/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            Run MRP
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as MrpRunStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="RUNNING">Running</option>
          <option value="COMPLETED">Completed</option>
          <option value="FAILED">Failed</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/manufacturing/mrp/runs/$runId", params: { runId: row.id } })}
          loading={runs.isPending}
          emptyMessage="No MRP runs yet."
          hasMore={runs.hasNextPage}
          onLoadMore={() => void runs.fetchNextPage()}
          loadingMore={runs.isFetchingNextPage}
          label="MRP runs"
        />
      </div>
    </div>
  );
}
