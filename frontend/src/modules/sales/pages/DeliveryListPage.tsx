/**
 * Deliveries list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useCustomerOptions, useDeliveries } from "@/modules/sales/hooks";
import type { Delivery, DeliveryStatus } from "@/modules/sales/types";

export function DeliveryListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("sales.delivery.manage");
  const [status, setStatus] = useState<DeliveryStatus | "">("");

  const deliveries = useDeliveries(status ? { status } : {});
  const customers = useCustomerOptions();
  const rows = deliveries.data?.pages.flatMap((page) => page.items) ?? [];

  const customerLabel = (id: string) => {
    const customer = customers.data?.items.find((c) => c.id === id);
    return customer ? `${customer.customer_code} — ${customer.name}` : id;
  };

  const columns: DataGridColumn<Delivery>[] = [
    { key: "delivery_number", header: "Delivery #", render: (row) => row.delivery_number, width: "140px" },
    { key: "customer_id", header: "Customer", render: (row) => customerLabel(row.customer_id) },
    { key: "delivery_date", header: "Delivery date", render: (row) => row.delivery_date, width: "120px" },
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Deliveries</h1>
        {canManage && (
          <Link
            to="/sales/deliveries/new"
            className="btn-ink"
          >
            New delivery
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as DeliveryStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="POSTED">Posted</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/sales/deliveries/$deliveryId", params: { deliveryId: row.id } })}
          loading={deliveries.isPending}
          emptyMessage="No deliveries yet."
          hasMore={deliveries.hasNextPage}
          onLoadMore={() => void deliveries.fetchNextPage()}
          loadingMore={deliveries.isFetchingNextPage}
          label="Deliveries"
        />
      </div>
    </div>
  );
}
