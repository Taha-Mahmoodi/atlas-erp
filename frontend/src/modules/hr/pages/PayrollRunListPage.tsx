/**
 * Payroll runs list (STRUCTURE §4; PLAN 10.4, D-055). Filterable by status, keyset-paginated
 * (D-014); row click opens the run workbench. `run_number` is claimed at posting (D-012), so a
 * draft shows a dash. The D-055 non-compliance disclaimer heads every payroll page.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { usePayrollRuns } from "@/modules/hr/hooks";
import type { PayrollRun, PayrollRunStatus } from "@/modules/hr/types";

const STATUS_TONE: Record<PayrollRunStatus, string> = {
  DRAFT: "bg-panel text-ink-muted",
  POSTED: "bg-success-tint text-success",
  CANCELLED: "bg-panel text-ink-muted",
};

export function PayrollRunStatusChip({ status }: { status: PayrollRunStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

/** The D-055 non-compliance flag the backend carries — surfaced verbatim on every payroll page. */
export function PayrollDisclaimer() {
  return (
    <p className="mt-4 rounded-control bg-warn-tint px-3 py-2 text-xs text-warn">
      Atlas v1 payroll is a simplistic, NOT jurisdiction-compliant gross-to-net calculation: a
      single flat withholding rate — no tax brackets, no social security, no deductions, no
      statutory reporting. Suitable for demos and the payroll-to-GL integration, never for paying
      real employees.
    </p>
  );
}

const COLUMNS: DataGridColumn<PayrollRun>[] = [
  { key: "run_number", header: "Run #", render: (row) => row.run_number ?? "—", width: "130px" },
  { key: "period_start", header: "Period from", render: (row) => row.period_start, width: "110px" },
  { key: "period_end", header: "Period to", render: (row) => row.period_end, width: "110px" },
  { key: "pay_date", header: "Pay date", render: (row) => row.pay_date, width: "110px" },
  { key: "employee_count", header: "Employees", align: "right", render: (row) => String(row.employee_count), width: "90px" },
  {
    key: "total_gross",
    header: "Gross",
    align: "right",
    render: (row) => formatMoney(row.total_gross, row.currency_code),
    width: "130px",
  },
  {
    key: "total_net",
    header: "Net",
    align: "right",
    render: (row) => formatMoney(row.total_net, row.currency_code),
    width: "130px",
  },
  { key: "status", header: "Status", render: (row) => <PayrollRunStatusChip status={row.status} />, width: "100px" },
];

export function PayrollRunListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("hr.payroll.manage");
  const [status, setStatus] = useState<PayrollRunStatus | "">("");

  const runs = usePayrollRuns(status ? { status } : {});
  const rows = runs.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Payroll Runs</h1>
        {canManage && (
          <Link
            to="/hr/payroll-runs/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New payroll run
          </Link>
        )}
      </div>

      <PayrollDisclaimer />

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as PayrollRunStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="POSTED">Posted</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/hr/payroll-runs/$runId", params: { runId: row.id } })}
          loading={runs.isPending}
          emptyMessage="No payroll runs yet."
          hasMore={runs.hasNextPage}
          onLoadMore={() => void runs.fetchNextPage()}
          loadingMore={runs.isFetchingNextPage}
          label="Payroll runs"
        />
      </div>
    </div>
  );
}
