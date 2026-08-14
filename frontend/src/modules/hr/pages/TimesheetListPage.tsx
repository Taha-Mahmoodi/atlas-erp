/**
 * Timesheets list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014); row click
 * opens the timesheet workbench.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useEmployeeOptions, useTimesheets } from "@/modules/hr/hooks";
import type { Timesheet, TimesheetStatus } from "@/modules/hr/types";

export function TimesheetListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("hr.timesheet.manage");
  const [status, setStatus] = useState<TimesheetStatus | "">("");

  const timesheets = useTimesheets(status ? { status } : {});
  const employees = useEmployeeOptions();
  const rows = timesheets.data?.pages.flatMap((page) => page.items) ?? [];

  const employeeLabel = (id: string) => {
    const employee = employees.data?.items.find((e) => e.id === id);
    return employee ? `${employee.employee_code} — ${employee.first_name} ${employee.last_name}` : id;
  };

  const columns: DataGridColumn<Timesheet>[] = [
    { key: "timesheet_number", header: "Timesheet #", render: (row) => row.timesheet_number, width: "130px" },
    { key: "employee_id", header: "Employee", render: (row) => employeeLabel(row.employee_id) },
    { key: "period_start", header: "From", render: (row) => row.period_start, width: "110px" },
    { key: "period_end", header: "To", render: (row) => row.period_end, width: "110px" },
    {
      key: "total_hours",
      header: "Hours",
      align: "right",
      render: (row) => formatQuantity(row.total_hours),
      width: "80px",
    },
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Timesheets</h1>
        {canManage && (
          <Link
            to="/hr/timesheets/new"
            className="btn-ink"
          >
            New timesheet
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as TimesheetStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="SUBMITTED">Submitted</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/hr/timesheets/$timesheetId", params: { timesheetId: row.id } })}
          loading={timesheets.isPending}
          emptyMessage="No timesheets yet."
          hasMore={timesheets.hasNextPage}
          onLoadMore={() => void timesheets.fetchNextPage()}
          loadingMore={timesheets.isFetchingNextPage}
          label="Timesheets"
        />
      </div>
    </div>
  );
}
