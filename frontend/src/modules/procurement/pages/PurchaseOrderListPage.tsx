/**
 * Purchase orders list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { usePurchaseOrders, useVendorLookup } from "@/modules/procurement/hooks";
import type { PurchaseOrder, PurchaseOrderStatus } from "@/modules/procurement/types";

const STATUS_TONE: Record<PurchaseOrderStatus, string> = {
  DRAFT: "bg-panel text-ink-muted",
  PENDING_APPROVAL: "bg-warn-tint text-warn",
  APPROVED: "bg-primary-tint text-primary",
  REJECTED: "bg-danger-tint text-danger",
  SENT: "bg-primary-tint text-primary",
  PARTIALLY_RECEIVED: "bg-warn-tint text-warn",
  RECEIVED: "bg-success-tint text-success",
  CLOSED: "bg-success-tint text-success",
  CANCELLED: "bg-panel text-ink-muted",
};

function StatusChip({ status }: { status: PurchaseOrderStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status.replace("_", " ")}
    </span>
  );
}

export function PurchaseOrderListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("procurement.po.manage");
  const [status, setStatus] = useState<PurchaseOrderStatus | "">("");

  const orders = usePurchaseOrders(status ? { status } : {});
  const vendors = useVendorLookup();
  const rows = orders.data?.pages.flatMap((page) => page.items) ?? [];

  const vendorLabel = (id: string) => {
    const vendor = vendors.data?.items.find((v) => v.id === id);
    return vendor ? `${vendor.vendor_code} — ${vendor.name}` : id;
  };

  const columns: DataGridColumn<PurchaseOrder>[] = [
    { key: "po_number", header: "PO #", render: (row) => row.po_number, width: "140px" },
    { key: "vendor_id", header: "Vendor", render: (row) => vendorLabel(row.vendor_id) },
    {
      key: "total_amount",
      header: "Total",
      align: "right",
      render: (row) => formatMoney(row.total_amount, row.currency_code),
      width: "140px",
    },
    { key: "expected_date", header: "Expected", render: (row) => row.expected_date ?? "—", width: "120px" },
    { key: "status", header: "Status", render: (row) => <StatusChip status={row.status} />, width: "150px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Purchase Orders</h1>
        {canManage && (
          <Link
            to="/procurement/purchase-orders/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New purchase order
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as PurchaseOrderStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="PENDING_APPROVAL">Pending approval</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
          <option value="SENT">Sent</option>
          <option value="PARTIALLY_RECEIVED">Partially received</option>
          <option value="RECEIVED">Received</option>
          <option value="CLOSED">Closed</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/procurement/purchase-orders/$purchaseOrderId", params: { purchaseOrderId: row.id } })}
          loading={orders.isPending}
          emptyMessage="No purchase orders yet."
          hasMore={orders.hasNextPage}
          onLoadMore={() => void orders.fetchNextPage()}
          loadingMore={orders.isFetchingNextPage}
          label="Purchase orders"
        />
      </div>
    </div>
  );
}
