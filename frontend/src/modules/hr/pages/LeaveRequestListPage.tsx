/**
 * Leave requests list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014); row
 * click opens the request workbench.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useEmployeeOptions, useLeaveRequests, useLeaveTypeOptions } from "@/modules/hr/hooks";
import type { LeaveRequest, LeaveRequestStatus } from "@/modules/hr/types";

export function LeaveRequestListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canRequest = (me.data?.permissions ?? []).includes("hr.leave.request");
  const [status, setStatus] = useState<LeaveRequestStatus | "">("");

  const requests = useLeaveRequests(status ? { status } : {});
  const employees = useEmployeeOptions();
  const leaveTypes = useLeaveTypeOptions();
  const rows = requests.data?.pages.flatMap((page) => page.items) ?? [];

  const employeeLabel = (id: string) => {
    const employee = employees.data?.items.find((e) => e.id === id);
    return employee ? `${employee.employee_code} — ${employee.first_name} ${employee.last_name}` : id;
  };
  const leaveTypeLabel = (id: string) => {
    const leaveType = leaveTypes.data?.items.find((t) => t.id === id);
    return leaveType ? leaveType.name : id;
  };

  const columns: DataGridColumn<LeaveRequest>[] = [
    { key: "request_number", header: "Request #", render: (row) => row.request_number, width: "130px" },
    { key: "employee_id", header: "Employee", render: (row) => employeeLabel(row.employee_id) },
    { key: "leave_type_id", header: "Leave type", render: (row) => leaveTypeLabel(row.leave_type_id), width: "140px" },
    { key: "start_date", header: "From", render: (row) => row.start_date, width: "110px" },
    { key: "end_date", header: "To", render: (row) => row.end_date, width: "110px" },
    { key: "days", header: "Days", align: "right", render: (row) => formatQuantity(row.days), width: "70px" },
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/hr">HR</Link> / <span className="text-ink">Leave requests</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Leave Requests</h1>
          <div className="flex items-center gap-2.5">
            {canRequest && (
              <Link
                to="/hr/leave-requests/new"
                className="btn-ink"
              >
                New request
              </Link>
            )}
          </div>
        </div>
      </header>

      <div>
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as LeaveRequestStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="SUBMITTED">Submitted</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/hr/leave-requests/$requestId", params: { requestId: row.id } })}
          loading={requests.isPending}
          emptyMessage="No leave requests yet."
          isFiltered={Boolean(status)}
          onClearFilters={() => setStatus("")}
          hasMore={requests.hasNextPage}
          onLoadMore={() => void requests.fetchNextPage()}
          loadingMore={requests.isFetchingNextPage}
          label="Leave requests"
        />
      </div>
    </div>
  );
}
