/**
 * Requisitions list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useRequisitions } from "@/modules/procurement/hooks";
import type { Requisition, RequisitionStatus } from "@/modules/procurement/types";

const STATUS_TONE: Record<RequisitionStatus, string> = {
  DRAFT: "bg-panel text-ink-muted",
  SUBMITTED: "bg-warn-tint text-warn",
  APPROVED: "bg-success-tint text-success",
  REJECTED: "bg-danger-tint text-danger",
  CONVERTED: "bg-primary-tint text-primary",
  CANCELLED: "bg-panel text-ink-muted",
};

function StatusChip({ status }: { status: RequisitionStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

const COLUMNS: DataGridColumn<Requisition>[] = [
  { key: "requisition_number", header: "Requisition #", render: (row) => row.requisition_number, width: "160px" },
  { key: "needed_by_date", header: "Needed by", render: (row) => row.needed_by_date ?? "—", width: "120px" },
  { key: "notes", header: "Notes", render: (row) => row.notes ?? "—" },
  { key: "status", header: "Status", render: (row) => <StatusChip status={row.status} />, width: "110px" },
];

export function RequisitionListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("procurement.requisition.manage");
  const [status, setStatus] = useState<RequisitionStatus | "">("");

  const requisitions = useRequisitions(status ? { status } : {});
  const rows = requisitions.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Requisitions</h1>
        {canManage && (
          <Link
            to="/procurement/requisitions/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New requisition
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as RequisitionStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="SUBMITTED">Submitted</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
          <option value="CONVERTED">Converted</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/procurement/requisitions/$requisitionId", params: { requisitionId: row.id } })}
          loading={requisitions.isPending}
          emptyMessage="No requisitions yet."
          hasMore={requisitions.hasNextPage}
          onLoadMore={() => void requisitions.fetchNextPage()}
          loadingMore={requisitions.isFetchingNextPage}
          label="Requisitions"
        />
      </div>
    </div>
  );
}
