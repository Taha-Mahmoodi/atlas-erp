/**
 * Warehouses list (STRUCTURE §4). Keyset-paginated (D-014); row click opens edit.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useWarehouses } from "@/modules/inventory/hooks";
import type { Warehouse } from "@/modules/inventory/types";
import { StatusPill } from "@/components/StatusPill";

const COLUMNS: DataGridColumn<Warehouse>[] = [
  { key: "code", header: "Code", render: (row) => row.code, width: "120px" },
  { key: "name", header: "Name", render: (row) => row.name },
  {
    key: "is_active",
    header: "Status",
    render: (row) => (
      <StatusPill status={row.is_active ? "ACTIVE" : "INACTIVE"} />
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
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/inventory">Inventory</Link> / <span className="text-ink">Warehouses</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Warehouses</h1>
          <div className="flex items-center gap-2.5">
            {canManage && (
              <Link
                to="/inventory/warehouses/new"
                className="btn-ink"
              >
                New warehouse
              </Link>
            )}
          </div>
        </div>
      </header>

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
