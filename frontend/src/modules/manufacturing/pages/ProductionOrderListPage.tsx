/**
 * Production orders list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014); row
 * click opens the workbench. Orders are numbered documents (MO-…) — created via the form,
 * advanced only by lifecycle actions on the detail page.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useItemLookup } from "@/modules/inventory/hooks";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useProductionOrders } from "@/modules/manufacturing/hooks";
import type { ProductionOrder, ProductionOrderStatus } from "@/modules/manufacturing/types";

const STATUS_TONE: Record<ProductionOrderStatus, string> = {
  DRAFT: "bg-panel text-ink-muted",
  RELEASED: "bg-primary-tint text-primary",
  IN_PROGRESS: "bg-warn-tint text-warn",
  FINISHED: "bg-success-tint text-success",
  CANCELLED: "bg-panel text-ink-muted",
};

export function OrderStatusChip({ status }: { status: ProductionOrderStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status.replace("_", " ")}
    </span>
  );
}

export function ProductionOrderListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("manufacturing.production_order.manage");
  const [status, setStatus] = useState<ProductionOrderStatus | "">("");

  const orders = useProductionOrders(status ? { status } : {});
  const items = useItemLookup();
  const rows = orders.data?.pages.flatMap((page) => page.items) ?? [];

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };

  const columns: DataGridColumn<ProductionOrder>[] = [
    { key: "order_number", header: "Order", render: (row) => row.order_number, width: "140px" },
    { key: "item_id", header: "Item", render: (row) => itemLabel(row.item_id) },
    {
      key: "quantity",
      header: "Quantity",
      align: "right",
      render: (row) => formatQuantity(row.quantity),
      width: "110px",
    },
    {
      key: "finished_quantity",
      header: "Finished",
      align: "right",
      render: (row) => formatQuantity(row.finished_quantity),
      width: "110px",
    },
    {
      key: "planned_start_date",
      header: "Planned start",
      render: (row) => row.planned_start_date ?? "—",
      width: "120px",
    },
    { key: "status", header: "Status", render: (row) => <OrderStatusChip status={row.status} />, width: "120px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Production Orders</h1>
        {canManage && (
          <Link
            to="/manufacturing/production-orders/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New production order
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as ProductionOrderStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="RELEASED">Released</option>
          <option value="IN_PROGRESS">In progress</option>
          <option value="FINISHED">Finished</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) =>
            void navigate({ to: "/manufacturing/production-orders/$orderId", params: { orderId: row.id } })
          }
          loading={orders.isPending}
          emptyMessage="No production orders yet."
          hasMore={orders.hasNextPage}
          onLoadMore={() => void orders.fetchNextPage()}
          loadingMore={orders.isFetchingNextPage}
          label="Production orders"
        />
      </div>
    </div>
  );
}
