/**
 * Stock counts list (STRUCTURE §4). Filterable by status; row click opens the count's
 * workbench (record quantities, preview variance, post or cancel).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatDate } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useStockCounts, useWarehouseLookup } from "@/modules/inventory/hooks";
import type { CountStatus, StockCount } from "@/modules/inventory/types";

const STATUS_TONE: Record<CountStatus, string> = {
  DRAFT: "bg-warn-tint text-warn",
  COUNTING: "bg-warn-tint text-warn",
  POSTED: "bg-success-tint text-success",
  CANCELLED: "bg-panel text-ink-muted",
};

function StatusChip({ status }: { status: CountStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

export function StockCountListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("inventory.count.manage");
  const warehouses = useWarehouseLookup();
  const [status, setStatus] = useState<CountStatus | "">("");

  const counts = useStockCounts(status ? { status } : {});
  const rows = counts.data?.items ?? [];

  const warehouseLabel = (id: string) => {
    const warehouse = warehouses.data?.items.find((w) => w.id === id);
    return warehouse ? `${warehouse.code} — ${warehouse.name}` : id;
  };

  const columns: DataGridColumn<StockCount>[] = [
    { key: "count_number", header: "Count #", render: (row) => row.count_number, width: "150px" },
    { key: "count_type", header: "Type", render: (row) => row.count_type, width: "100px" },
    { key: "warehouse_id", header: "Warehouse", render: (row) => warehouseLabel(row.warehouse_id) },
    { key: "count_date", header: "Date", render: (row) => formatDate(row.count_date), width: "120px" },
    { key: "status", header: "Status", render: (row) => <StatusChip status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Stock Counts</h1>
        {canManage && (
          <Link
            to="/inventory/stock-counts/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New count
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as CountStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="COUNTING">Counting</option>
          <option value="POSTED">Posted</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/inventory/stock-counts/$countId", params: { countId: row.id } })}
          loading={counts.isPending}
          emptyMessage="No stock counts yet."
          label="Stock counts"
        />
      </div>
    </div>
  );
}
