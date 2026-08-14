/**
 * Leave types list (STRUCTURE §4). Keyset-paginated (D-014); row click opens edit.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useLeaveTypes } from "@/modules/hr/hooks";
import type { LeaveType } from "@/modules/hr/types";

const COLUMNS: DataGridColumn<LeaveType>[] = [
  { key: "code", header: "Code", render: (row) => row.code, width: "110px" },
  { key: "name", header: "Name", render: (row) => row.name },
  { key: "accrual_frequency", header: "Accrual", render: (row) => row.accrual_frequency, width: "100px" },
  {
    key: "accrual_amount",
    header: "Days / period",
    align: "right",
    render: (row) => formatQuantity(row.accrual_amount),
    width: "110px",
  },
  {
    key: "max_balance",
    header: "Max balance",
    align: "right",
    render: (row) => (row.max_balance !== null ? formatQuantity(row.max_balance) : "—"),
    width: "110px",
  },
  { key: "is_paid", header: "Paid", render: (row) => (row.is_paid ? "Yes" : "No"), width: "70px" },
  { key: "is_active", header: "Active", render: (row) => (row.is_active ? "Yes" : "No"), width: "80px" },
];

export function LeaveTypeListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("hr.leave_type.manage");

  const leaveTypes = useLeaveTypes();
  const rows = leaveTypes.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Leave Types</h1>
        {canManage && (
          <Link
            to="/hr/leave-types/new"
            className="btn-ink"
          >
            New leave type
          </Link>
        )}
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/hr/leave-types/$leaveTypeId", params: { leaveTypeId: row.id } })}
          loading={leaveTypes.isPending}
          emptyMessage="No leave types yet."
          hasMore={leaveTypes.hasNextPage}
          onLoadMore={() => void leaveTypes.fetchNextPage()}
          loadingMore={leaveTypes.isFetchingNextPage}
          label="Leave types"
        />
      </div>
    </div>
  );
}
