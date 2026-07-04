/**
 * Sales orders list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useCustomerOptions, useSalesOrders } from "@/modules/sales/hooks";
import type { SalesOrder, SalesOrderStatus } from "@/modules/sales/types";

const STATUS_TONE: Record<SalesOrderStatus, string> = {
  DRAFT: "bg-panel text-ink-muted",
  CONFIRMED: "bg-success-tint text-success",
  CREDIT_BLOCKED: "bg-danger-tint text-danger",
  PARTIALLY_DELIVERED: "bg-warn-tint text-warn",
  DELIVERED: "bg-primary-tint text-primary",
  INVOICED: "bg-primary-tint text-primary",
  CLOSED: "bg-panel text-ink-muted",
  CANCELLED: "bg-panel text-ink-muted",
};

function StatusChip({ status }: { status: SalesOrderStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

export function SalesOrderListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("sales.order.manage");
  const [status, setStatus] = useState<SalesOrderStatus | "">("");

  const orders = useSalesOrders(status ? { status } : {});
  const customers = useCustomerOptions();
  const rows = orders.data?.pages.flatMap((page) => page.items) ?? [];

  const customerLabel = (id: string) => {
    const customer = customers.data?.items.find((c) => c.id === id);
    return customer ? `${customer.customer_code} — ${customer.name}` : id;
  };

  const columns: DataGridColumn<SalesOrder>[] = [
    { key: "order_number", header: "Order #", render: (row) => row.order_number, width: "140px" },
    { key: "customer_id", header: "Customer", render: (row) => customerLabel(row.customer_id) },
    {
      key: "total_amount",
      header: "Total",
      align: "right",
      render: (row) => formatMoney(row.total_amount, row.currency_code),
      width: "140px",
    },
    { key: "status", header: "Status", render: (row) => <StatusChip status={row.status} />, width: "150px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Sales Orders</h1>
        {canManage && (
          <Link
            to="/sales/orders/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New order
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as SalesOrderStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="CONFIRMED">Confirmed</option>
          <option value="CREDIT_BLOCKED">Credit blocked</option>
          <option value="PARTIALLY_DELIVERED">Partially delivered</option>
          <option value="DELIVERED">Delivered</option>
          <option value="INVOICED">Invoiced</option>
          <option value="CLOSED">Closed</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/sales/orders/$orderId", params: { orderId: row.id } })}
          loading={orders.isPending}
          emptyMessage="No sales orders yet."
          hasMore={orders.hasNextPage}
          onLoadMore={() => void orders.fetchNextPage()}
          loadingMore={orders.isFetchingNextPage}
          label="Sales orders"
        />
      </div>
    </div>
  );
}
