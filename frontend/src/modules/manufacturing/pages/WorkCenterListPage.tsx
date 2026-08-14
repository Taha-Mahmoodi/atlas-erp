/**
 * Work centers list (STRUCTURE §4). Filterable by active status, keyset-paginated (D-014);
 * row click opens edit. There's no delete endpoint — deactivation is a PATCH, not a separate
 * action.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatPercent, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useWorkCenters } from "@/modules/manufacturing/hooks";
import type { WorkCenter } from "@/modules/manufacturing/types";
import { StatusPill } from "@/components/StatusPill";

const COLUMNS: DataGridColumn<WorkCenter>[] = [
  { key: "code", header: "Code", render: (row) => row.code, width: "120px" },
  { key: "name", header: "Name", render: (row) => row.name },
  {
    key: "capacity_hours_per_day",
    header: "Capacity (hrs/day)",
    align: "right",
    render: (row) => formatQuantity(row.capacity_hours_per_day),
    width: "160px",
  },
  {
    key: "efficiency_percent",
    header: "Efficiency",
    align: "right",
    render: (row) => formatPercent(row.efficiency_percent),
    width: "100px",
  },
  {
    key: "is_active",
    header: "Status",
    render: (row) => (
      <StatusPill status={row.is_active ? "ACTIVE" : "INACTIVE"} />
    ),
    width: "100px",
  },
];

export function WorkCenterListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("manufacturing.workcenter.manage");
  const [activeOnly, setActiveOnly] = useState<"" | "true" | "false">("");

  const workCenters = useWorkCenters(activeOnly ? { is_active: activeOnly === "true" } : {});
  const rows = workCenters.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/manufacturing">Manufacturing</Link> /{" "}
          <span className="text-ink">Work Centers</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Work Centers</h1>
          <div className="flex items-center gap-2.5">
            {canManage && (
              <Link
                to="/manufacturing/work-centers/new"
                className="btn-ink"
              >
                New work center
              </Link>
            )}
          </div>
        </div>
      </header>

      <div className="mt-4">
        <select
          value={activeOnly}
          onChange={(event) => setActiveOnly(event.target.value as "" | "true" | "false")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All</option>
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/manufacturing/work-centers/$workCenterId", params: { workCenterId: row.id } })}
          loading={workCenters.isPending}
          emptyMessage="No work centers yet."
          isFiltered={Boolean(activeOnly)}
          onClearFilters={() => setActiveOnly("")}
          hasMore={workCenters.hasNextPage}
          onLoadMore={() => void workCenters.fetchNextPage()}
          loadingMore={workCenters.isFetchingNextPage}
          label="Work centers"
        />
      </div>
    </div>
  );
}
