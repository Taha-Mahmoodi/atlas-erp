/**
 * Inspection lots list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014); row
 * click opens the decision workbench. No "New" button — lots are auto-created by posting a
 * goods receipt whose line is flagged `requires_inspection`, never via the API.
 */

import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatDate, formatQuantity } from "@/lib/format";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useItemLookup } from "@/modules/inventory/hooks";
import { useInspectionLots } from "@/modules/quality/hooks";
import type { InspectionLot, InspectionLotStatus } from "@/modules/quality/types";

const STATUS_TONE: Record<InspectionLotStatus, string> = {
  OPEN: "bg-primary-tint text-primary",
  ACCEPTED: "bg-success-tint text-success",
  REJECTED: "bg-danger-tint text-danger",
  CANCELLED: "bg-panel text-ink-muted",
};

function StatusChip({ status }: { status: InspectionLotStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

export function InspectionLotListPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<InspectionLotStatus | "">("");

  const lots = useInspectionLots(status ? { status } : {});
  const items = useItemLookup();
  const rows = lots.data?.pages.flatMap((page) => page.items) ?? [];

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };

  const columns: DataGridColumn<InspectionLot>[] = [
    { key: "lot_number", header: "Lot", render: (row) => row.lot_number, width: "140px" },
    { key: "item", header: "Item", render: (row) => itemLabel(row.item_id) },
    {
      key: "quantity",
      header: "Quantity",
      render: (row) => formatQuantity(row.quantity),
      align: "right",
      width: "110px",
    },
    {
      key: "created_date",
      header: "Created",
      render: (row) => formatDate(row.created_date),
      width: "120px",
    },
    {
      key: "decided_date",
      header: "Decided",
      render: (row) => (row.decided_date ? formatDate(row.decided_date) : "—"),
      width: "120px",
    },
    {
      key: "disposition",
      header: "Disposition",
      render: (row) => row.disposition ?? "—",
      width: "110px",
    },
    { key: "status", header: "Status", render: (row) => <StatusChip status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <h1 className="text-xl font-semibold text-ink">Inspection lots</h1>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as InspectionLotStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="OPEN">Open</option>
          <option value="ACCEPTED">Accepted</option>
          <option value="REJECTED">Rejected</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/quality/inspection-lots/$lotId", params: { lotId: row.id } })}
          loading={lots.isPending}
          emptyMessage="No inspection lots. Posting a goods receipt with a line flagged for inspection creates one."
          hasMore={lots.hasNextPage}
          onLoadMore={() => void lots.fetchNextPage()}
          loadingMore={lots.isFetchingNextPage}
          label="Inspection lots"
        />
      </div>
    </div>
  );
}
