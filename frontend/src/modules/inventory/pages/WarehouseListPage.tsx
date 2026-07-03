/**
 * Warehouses list (STRUCTURE §4). Keyset-paginated (D-014); row click opens edit.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useWarehouses } from "@/modules/inventory/hooks";
import type { Warehouse } from "@/modules/inventory/types";

const COLUMNS: DataGridColumn<Warehouse>[] = [
  { key: "code", header: "Code", render: (row) => row.code, width: "120px" },
  { key: "name", header: "Name", render: (row) => row.name },
  {
    key: "is_active",
    header: "Status",
    render: (row) => (
      <span
        className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${
          row.is_active ? "bg-success-tint text-success" : "bg-panel text-ink-muted"
        }`}
      >
        {row.is_active ? "Active" : "Inactive"}
      </span>
    ),
    width: "100px",
  },
];

export function WarehouseListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("inventory.warehouse.manage");
  const warehouses = useWarehouses();
  const rows = warehouses.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Warehouses</h1>
        {canManage && (
          <Link
            to="/inventory/warehouses/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New warehouse
          </Link>
        )}
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/inventory/warehouses/$warehouseId", params: { warehouseId: row.id } })}
          loading={warehouses.isPending}
          emptyMessage="No warehouses yet."
          hasMore={warehouses.hasNextPage}
          onLoadMore={() => void warehouses.fetchNextPage()}
          loadingMore={warehouses.isFetchingNextPage}
          label="Warehouses"
        />
      </div>
    </div>
  );
}
