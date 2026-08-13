/**
 * Leave requests list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014); row
 * click opens the request workbench.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useEmployeeOptions, useLeaveRequests, useLeaveTypeOptions } from "@/modules/hr/hooks";
import type { LeaveRequest, LeaveRequestStatus } from "@/modules/hr/types";

const STATUS_TONE: Record<LeaveRequestStatus, string> = {
  DRAFT: "bg-panel text-ink-muted",
  SUBMITTED: "bg-primary-tint text-primary",
  APPROVED: "bg-success-tint text-success",
  REJECTED: "bg-danger-tint text-danger",
  CANCELLED: "bg-panel text-ink-muted",
};

export function LeaveRequestStatusChip({ status }: { status: LeaveRequestStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

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
    { key: "status", header: "Status", render: (row) => <LeaveRequestStatusChip status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Leave Requests</h1>
        {canRequest && (
          <Link
            to="/hr/leave-requests/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New request
          </Link>
        )}
      </div>

      <div className="mt-4">
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
          hasMore={requests.hasNextPage}
          onLoadMore={() => void requests.fetchNextPage()}
          loadingMore={requests.isFetchingNextPage}
          label="Leave requests"
        />
      </div>
    </div>
  );
}
