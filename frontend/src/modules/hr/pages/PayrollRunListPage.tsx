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
import { StatusPill } from "@/components/StatusPill";
import { usePayrollRuns } from "@/modules/hr/hooks";
import type { PayrollRun, PayrollRunStatus } from "@/modules/hr/types";

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
  { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "100px" },
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
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/hr">HR</Link> / <span className="text-ink">Payroll runs</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Payroll Runs</h1>
          <div className="flex items-center gap-2.5">
            {canManage && (
              <Link
                to="/hr/payroll-runs/new"
                className="btn-ink"
              >
                New payroll run
              </Link>
            )}
          </div>
        </div>
      </header>

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
          isFiltered={Boolean(status)}
          onClearFilters={() => setStatus("")}
          hasMore={runs.hasNextPage}
          onLoadMore={() => void runs.fetchNextPage()}
          loadingMore={runs.isFetchingNextPage}
          label="Payroll runs"
        />
      </div>
    </div>
  );
}
