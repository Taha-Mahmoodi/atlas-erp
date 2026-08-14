/**
 * Preventive maintenance plans list (STRUCTURE §4). Filterable by status, keyset-paginated
 * (D-014); row click opens edit. "Run preventive" executes the generation run: every ACTIVE
 * plan due on/before today spawns one PREVENTIVE order and advances past the run date — a
 * same-day re-run finds nothing due (naturally idempotent).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDate } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import {
  useEquipmentLookup,
  useMaintenancePlans,
  useRunPreventiveMaintenance,
} from "@/modules/maintenance/hooks";
import type {
  MaintenancePlan,
  MaintenancePlanStatus,
  RunPreventiveResult,
} from "@/modules/maintenance/types";

function intervalLabel(plan: MaintenancePlan): string {
  const unit = plan.interval_unit.toLowerCase();
  return `Every ${plan.interval_value} ${plan.interval_value === 1 ? unit.slice(0, -1) : unit}`;
}

export function MaintenancePlanListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const canManage = permissions.includes("maintenance.plan.manage");
  const canRun = permissions.includes("maintenance.plan.run");
  const [status, setStatus] = useState<MaintenancePlanStatus | "">("");

  const plans = useMaintenancePlans(status ? { status } : {});
  const equipment = useEquipmentLookup();
  const runPreventive = useRunPreventiveMaintenance();
  const [runResult, setRunResult] = useState<RunPreventiveResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const rows = plans.data?.pages.flatMap((page) => page.items) ?? [];

  const equipmentLabel = (id: string) => {
    const unit = equipment.data?.items.find((e) => e.id === id);
    return unit ? `${unit.code} — ${unit.name}` : id;
  };

  const run = async () => {
    setError(null);
    setRunResult(null);
    try {
      setRunResult(await runPreventive.mutateAsync());
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to run preventive generation."));
    }
  };

  const columns: DataGridColumn<MaintenancePlan>[] = [
    { key: "code", header: "Code", render: (row) => row.code, width: "120px" },
    { key: "name", header: "Name", render: (row) => row.name },
    { key: "equipment", header: "Equipment", render: (row) => equipmentLabel(row.equipment_id) },
    { key: "interval", header: "Interval", render: (row) => intervalLabel(row), width: "140px" },
    {
      key: "next_due_date",
      header: "Next due",
      render: (row) => formatDate(row.next_due_date),
      width: "120px",
    },
    {
      key: "last_generated_date",
      header: "Last generated",
      render: (row) => (row.last_generated_date ? formatDate(row.last_generated_date) : "—"),
      width: "130px",
    },
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "100px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Preventive plans</h1>
        <div className="flex gap-2">
          {canRun && (
            <button
              type="button"
              onClick={() => void run()}
              disabled={runPreventive.isPending}
              className="btn-chip"
            >
              {runPreventive.isPending ? "Running…" : "Run preventive"}
            </button>
          )}
          {canManage && (
            <Link
              to="/maintenance/plans/new"
              className="btn-ink"
            >
              New plan
            </Link>
          )}
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      {runResult && (
        <p className="mt-4 rounded-control bg-success-tint px-3 py-2 text-xs text-success">
          {runResult.plans_due === 0
            ? `No plans were due as of ${formatDate(runResult.as_of_date)}.`
            : `${runResult.plans_due} plan${runResult.plans_due === 1 ? "" : "s"} due — ${runResult.orders_generated.length} preventive order${runResult.orders_generated.length === 1 ? "" : "s"} generated. `}
          {runResult.plans_due > 0 && (
            <Link to="/maintenance/orders" className="underline">
              View orders
            </Link>
          )}
        </p>
      )}

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as MaintenancePlanStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/maintenance/plans/$planId", params: { planId: row.id } })}
          loading={plans.isPending}
          emptyMessage="No preventive plans yet."
          hasMore={plans.hasNextPage}
          onLoadMore={() => void plans.fetchNextPage()}
          loadingMore={plans.isFetchingNextPage}
          label="Preventive plans"
        />
      </div>
    </div>
  );
}
