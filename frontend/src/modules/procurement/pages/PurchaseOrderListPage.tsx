/**
 * Purchase orders list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { usePurchaseOrders, useVendorLookup } from "@/modules/procurement/hooks";
import type { PurchaseOrder, PurchaseOrderStatus } from "@/modules/procurement/types";

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
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "150px" },
  ];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/procurement" className="hover:underline">
            Procurement
          </Link>{" "}
          / <span className="text-ink">Purchase Orders</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Purchase Orders</h1>
          <div className="flex items-center gap-2.5">
            {canManage && (
              <Link
                to="/procurement/purchase-orders/new"
                className="btn-ink"
              >
                New purchase order
              </Link>
            )}
          </div>
        </div>
      </header>

      <div>
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
          isFiltered={Boolean(status)}
          onClearFilters={() => setStatus("")}
          hasMore={orders.hasNextPage}
          onLoadMore={() => void orders.fetchNextPage()}
          loadingMore={orders.isFetchingNextPage}
          label="Purchase orders"
        />
      </div>
    </div>
  );
}
