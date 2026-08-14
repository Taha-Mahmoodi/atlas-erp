/**
 * Sales orders list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useCustomerOptions, useSalesOrders } from "@/modules/sales/hooks";
import type { SalesOrder, SalesOrderStatus } from "@/modules/sales/types";

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
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "150px" },
  ];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/sales">Sales</Link> / <span className="text-ink">Sales Orders</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Sales Orders</h1>
          <div className="flex items-center gap-2.5">
            {canManage && (
              <Link
                to="/sales/orders/new"
                className="btn-ink"
              >
                New order
              </Link>
            )}
          </div>
        </div>
      </header>

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
          isFiltered={Boolean(status)}
          onClearFilters={() => setStatus("")}
          hasMore={orders.hasNextPage}
          onLoadMore={() => void orders.fetchNextPage()}
          loadingMore={orders.isFetchingNextPage}
          label="Sales orders"
        />
      </div>
    </div>
  );
}
